import http.server
import socketserver
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union


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
    _call_count: int = field(default=0, init=False, repr=False)

    def next_status(self) -> int:
        if self.status_sequence:
            idx = min(self._call_count, len(self.status_sequence) - 1)
            code = self.status_sequence[idx]
        else:
            code = self.status_code
        self._call_count += 1
        return code


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

    def _resolve_payload(self, route: RouteBehavior, request_path: str) -> bytes:
        if route.body is not None:
            return (
                route.body.encode("utf-8")
                if isinstance(route.body, str)
                else bytes(route.body)
            )
        if route.file_path is not None and route.file_path.is_file():
            return route.file_path.read_bytes()
        clean_rel = request_path.split("?", 1)[0].lstrip("/")
        candidate = (self.directory / clean_rel).resolve()
        try:
            candidate.relative_to(self.directory.resolve())
        except ValueError:
            return b""
        if candidate.is_file():
            return candidate.read_bytes()
        return b""

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

                    status = route.next_status()
                    if route.redirect_to and status in (301, 302, 303, 307, 308):
                        self.send_response(status)
                        self.send_header("Location", route.redirect_to)
                        for k, v in route.headers.items():
                            self.send_header(k, v)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return True

                    payload = parent._resolve_payload(route, self.path)
                    full_len = len(payload)

                    if route.truncate_bytes is not None:
                        stream_bytes = payload[: route.truncate_bytes]
                    else:
                        stream_bytes = payload

                    self.send_response(status)
                    for k, v in route.headers.items():
                        self.send_header(k, v)

                    if not route.omit_content_length:
                        reported_len = (
                            route.content_length_override
                            if route.content_length_override is not None
                            else full_len
                        )
                        self.send_header("Content-Length", str(reported_len))

                    self.end_headers()

                    if is_head:
                        return True

                    try:
                        if route.chunk_size and route.chunk_size > 0:
                            for idx in range(0, len(stream_bytes), route.chunk_size):
                                chunk = stream_bytes[idx : idx + route.chunk_size]
                                self.wfile.write(chunk)
                                self.wfile.flush()
                                if route.chunk_delay_seconds > 0:
                                    time.sleep(route.chunk_delay_seconds)
                        else:
                            self.wfile.write(stream_bytes)
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
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
                target=self.server.serve_forever, daemon=True
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
