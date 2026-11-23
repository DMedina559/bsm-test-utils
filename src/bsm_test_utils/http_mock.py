import http.server
import json
import os
import re
import socketserver
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Union


@dataclass
class RecordedRequest:
    """Metadata captured for an incoming HTTP request."""

    method: str
    path: str
    headers: Dict[str, str]
    timestamp: float = field(default_factory=time.time)


@dataclass
class RouteBehavior:
    """Configurable response behavior for a specific HTTP route."""

    status_code: int = 200
    status_sequence: Optional[List[int]] = None
    body: Optional[Union[bytes, str]] = None
    file_path: Optional[Path] = None
    headers: Dict[str, str] = field(default_factory=dict)
    delay_seconds: float = 0.0
    chunk_size: Optional[int] = None
    chunk_delay_seconds: float = 0.0
    truncate_bytes: Optional[int] = None
    drop_connection: bool = False
    redirect_to: Optional[str] = None
    content_length_override: Optional[int] = None
    omit_content_length: bool = False
    accept_ranges: bool = False
    etag: Optional[str] = None
    _call_count: int = field(default=0, init=False, repr=False)

    def next_status(self) -> int:
        if self.status_sequence:
            idx = min(self._call_count, len(self.status_sequence) - 1)
            code = self.status_sequence[idx]
        else:
            code = self.status_code
        self._call_count += 1
        return code


def _byte_range(header: str, length: int) -> Optional[tuple[int, int]]:
    """Return a single range as start and exclusive stop, or None to ignore it."""
    match = re.fullmatch(r"bytes=([0-9]{0,20})-([0-9]{0,20})", header.strip())
    if match is None:
        return None
    first, last = match.groups()
    if not first and not last:
        return None
    if not first:
        return max(0, length - int(last)), length
    start = int(first)
    stop = min(length, int(last) + 1) if last else length
    return start, stop


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class MockHTTPServer:
    """
    A multithreaded mock HTTP server for testing file downloads, API endpoints,
    retries, throttling, truncated streams, and redirects.
    """

    def __init__(self, directory: Union[str, Path], port: int = 0):
        self.directory = Path(directory)
        self.port = port
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._routes: Dict[str, RouteBehavior] = {}
        self._requests: List[RecordedRequest] = []

    @property
    def requests(self) -> List[RecordedRequest]:
        """Returns a copy of recorded requests in arrival order."""
        with self._lock:
            return list(self._requests)

    def clear_requests(self) -> None:
        """Clears the recorded request log."""
        with self._lock:
            self._requests.clear()

    def clear_routes(self) -> None:
        """Removes all custom route behaviors."""
        with self._lock:
            self._routes.clear()

    def add_route(self, path: str, behavior: RouteBehavior) -> RouteBehavior:
        """Registers a custom RouteBehavior for a URL path (e.g., '/file.zip')."""
        norm_path = "/" + path.lstrip("/")
        with self._lock:
            self._routes[norm_path] = behavior
        return behavior

    def add_retry_route(
        self,
        path: str,
        fail_statuses: Sequence[int],
        final_status: int = 200,
        body: Optional[Union[bytes, str]] = None,
        file_path: Optional[Union[str, Path]] = None,
    ) -> RouteBehavior:
        """Configures a route that fails with fail_statuses before succeeding."""
        seq = list(fail_statuses) + [final_status]
        behavior = RouteBehavior(
            status_code=final_status,
            status_sequence=seq,
            body=body,
            file_path=Path(file_path) if file_path is not None else None,
        )
        return self.add_route(path, behavior)

    def _record_request(
        self, method: str, path: str, headers: Dict[str, str]
    ) -> Optional[RouteBehavior]:
        clean_path = path.split("?", 1)[0]
        with self._lock:
            self._requests.append(
                RecordedRequest(method=method, path=path, headers=headers)
            )
            return self._routes.get(clean_path)

    def _open_payload(self, route: RouteBehavior, request_path: str):
        if route.body is not None:
            body = (
                route.body.encode("utf-8")
                if isinstance(route.body, str)
                else route.body
            )
            return nullcontext(None), body
        if route.file_path is not None and route.file_path.is_file():
            return route.file_path.open("rb"), b""
        clean_rel = request_path.split("?", 1)[0].lstrip("/")
        candidate = (self.directory / clean_rel).resolve()
        if candidate.is_relative_to(self.directory.resolve()) and candidate.is_file():
            return candidate.open("rb"), b""
        return nullcontext(None), b""

    def start(self) -> "MockHTTPServer":
        """Starts the server in a background thread. Safe against duplicate calls."""
        with self._lock:
            if self.server is not None:
                return self

            parent = self

            class Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, directory=str(parent.directory), **kwargs):
                    super().__init__(*args, directory=directory, **kwargs)

                def log_message(self, format: str, *args) -> None:
                    # Suppress noisy console logging during test runs
                    pass

                def _send_empty_response(self, status: int, headers: Dict[str, str]):
                    self.send_response(status)
                    for key, value in headers.items():
                        self.send_header(key, value)
                    if status != 304:
                        self.send_header("Content-Length", "0")
                    self.end_headers()

                def _handle_custom_or_default(self, is_head: bool = False) -> bool:
                    hdrs = {k: v for k, v in self.headers.items()}
                    route = parent._record_request(self.command, self.path, hdrs)
                    if route is None:
                        return False

                    if route.delay_seconds > 0:
                        time.sleep(route.delay_seconds)

                    if route.drop_connection:
                        self.close_connection = True
                        try:
                            self.connection.close()
                        except OSError:
                            pass
                        return True

                    with parent._lock:
                        status = route.next_status()
                    if route.redirect_to and status in (301, 302, 303, 307, 308):
                        self.send_response(status)
                        self.send_header("Location", route.redirect_to)
                        for k, v in route.headers.items():
                            self.send_header(k, v)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return True

                    stream, body = parent._open_payload(route, self.path)
                    with stream as file:
                        full_len = (
                            os.fstat(file.fileno()).st_size if file else len(body)
                        )
                        headers = dict(route.headers)
                        if route.etag is not None:
                            headers["ETag"] = route.etag
                            validators = self.headers.get("If-None-Match", "").split(
                                ","
                            )
                            matches = any(
                                tag.strip() == "*"
                                or tag.strip().removeprefix("W/")
                                == route.etag.removeprefix("W/")
                                for tag in validators
                            )
                            if status == 200 and matches:
                                self._send_empty_response(304, headers)
                                return True

                        offset, end = 0, full_len
                        if route.accept_ranges:
                            headers["Accept-Ranges"] = "bytes"
                            if_range = self.headers.get("If-Range")
                            may_use_range = if_range is None or (
                                if_range == route.etag and not if_range.startswith("W/")
                            )
                            if status == 200 and not is_head and may_use_range:
                                requested = _byte_range(
                                    self.headers.get("Range", ""), full_len
                                )
                                if requested is not None:
                                    offset, end = requested
                                    if offset >= end:
                                        headers["Content-Range"] = f"bytes */{full_len}"
                                        self._send_empty_response(416, headers)
                                        return True
                                    status = 206
                                    headers["Content-Range"] = (
                                        f"bytes {offset}-{end - 1}/{full_len}"
                                    )

                        response_len = end - offset
                        self.send_response(status)
                        for key, value in headers.items():
                            self.send_header(key, value)
                        if not route.omit_content_length:
                            reported_len = route.content_length_override
                            self.send_header(
                                "Content-Length",
                                str(
                                    response_len
                                    if reported_len is None
                                    else reported_len
                                ),
                            )
                        self.end_headers()
                        if is_head:
                            return True

                        limit = route.truncate_bytes
                        if limit is None:
                            remaining = response_len
                        elif limit < 0:
                            remaining = max(0, response_len + limit)
                        else:
                            remaining = min(response_len, limit)
                        throttle = route.chunk_size is not None and route.chunk_size > 0
                        chunk_size = route.chunk_size if throttle else 64 * 1024
                        assert chunk_size is not None
                        if file and offset:
                            file.seek(offset)
                        try:
                            while remaining:
                                size = min(chunk_size, remaining)
                                chunk = (
                                    file.read(size)
                                    if file
                                    else body[offset : offset + size]
                                )
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                offset += len(chunk)
                                remaining -= len(chunk)
                                if throttle and route.chunk_delay_seconds > 0:
                                    self.wfile.flush()
                                    time.sleep(route.chunk_delay_seconds)
                        except OSError:
                            pass

                    if (
                        route.truncate_bytes is not None
                        or route.content_length_override is not None
                    ):
                        self.close_connection = True
                    return True

                def do_GET(self) -> None:
                    if not self._handle_custom_or_default(is_head=False):
                        super().do_GET()

                def do_HEAD(self) -> None:
                    if not self._handle_custom_or_default(is_head=True):
                        super().do_HEAD()

            self.server = _ThreadingTCPServer(("127.0.0.1", self.port), Handler)
            self.port = self.server.server_address[1]

            self.thread = threading.Thread(
                target=self.server.serve_forever,
                kwargs={"poll_interval": 0.02},
                daemon=True,
            )
            self.thread.start()
            return self

    def stop(self, timeout: float = 5.0) -> None:
        """Stops the server and cleans up socket/thread resources with bounded wait."""
        with self._lock:
            srv = self.server
            thr = self.thread
            self.server = None
            self.thread = None

        if srv is not None:
            try:
                srv.shutdown()
            finally:
                srv.server_close()

        if thr is not None and thr.is_alive():
            thr.join(timeout=timeout)

    def __enter__(self) -> "MockHTTPServer":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    @property
    def url(self) -> str:
        """Returns the base URL of the server."""
        return f"http://127.0.0.1:{self.port}"


class BedrockDownloadCatalog:
    """Publish configurable release links backed by reusable local archives."""

    def __init__(self, server: MockHTTPServer, archives: Mapping[str, Path]):
        self.server = server
        self.archives = dict(archives)

    def publish(
        self, *, stable: str = "1.26.45.1", preview: str = "1.26.60.23"
    ) -> MockHTTPServer:
        links = []
        releases = (
            ("windows", "win", "Windows", stable, False),
            ("linux", "linux", "Linux", stable, False),
            ("windows", "win", "Windows", preview, True),
            ("linux", "linux", "Linux", preview, True),
        )
        for platform, slug, download_type, version, is_preview in releases:
            suffix = "-preview" if is_preview else ""
            path = f"/bedrockdedicatedserver/bin-{slug}{suffix}/bedrock-server-{version}.zip"
            self.server.add_route(
                path, RouteBehavior(file_path=self.archives[platform])
            )
            links.append(
                {
                    "downloadType": f"serverBedrock{'Preview' if is_preview else ''}{download_type}",
                    "downloadUrl": f"{self.server.url}{path}",
                }
            )
        links.append(
            {
                "downloadType": "serverJar",
                "downloadUrl": f"{self.server.url}/server.jar",
            }
        )
        self.server.add_route(
            "/api/v1.0/download/links",
            RouteBehavior(
                body=json.dumps({"result": {"links": links}}),
                headers={"Content-Type": "application/json"},
            ),
        )
        return self.server
