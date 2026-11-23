import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pytest

from bsm_test_utils.http_mock import MockHTTPServer, RouteBehavior


def test_mock_http_server_lifecycle_and_context(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world", encoding="utf-8")

    with MockHTTPServer(directory=str(tmp_path)) as server:
        first_port = server.port
        # Repeated start() must not replace or leak the active server
        server.start()
        assert server.port == first_port

        url = f"{server.url}/test.txt"
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.status == 200
            assert response.read().decode("utf-8") == "hello world"

    # Stopping again is a safe no-op
    server.stop()


def test_mock_http_server_retry_redirect_and_recording(tmp_path):
    with MockHTTPServer(directory=tmp_path) as server:
        server.add_retry_route(
            "/flaky.txt",
            fail_statuses=[503, 502],
            final_status=200,
            body=b"recovered payload",
        )
        server.add_route(
            "/old-link",
            RouteBehavior(status_code=302, redirect_to=f"{server.url}/flaky.txt"),
        )

        # First two calls fail with 503 and 502
        with pytest.raises(urllib.error.HTTPError) as exc1:
            urllib.request.urlopen(f"{server.url}/flaky.txt", timeout=5)
        assert exc1.value.code == 503

        with pytest.raises(urllib.error.HTTPError) as exc2:
            urllib.request.urlopen(f"{server.url}/flaky.txt", timeout=5)
        assert exc2.value.code == 502

        # Third call via redirect succeeds with 200
        with urllib.request.urlopen(f"{server.url}/old-link", timeout=5) as resp:
            assert resp.status == 200
            assert resp.read() == b"recovered payload"

        paths = [r.path for r in server.requests]
        assert paths == ["/flaky.txt", "/flaky.txt", "/old-link", "/flaky.txt"]


def test_mock_http_server_truncation_headers_and_concurrency(tmp_path):
    payload = b"0123456789ABCDEF" * 64  # 1024 bytes
    with MockHTTPServer(directory=tmp_path) as server:
        server.add_route(
            "/truncated.bin",
            RouteBehavior(
                body=payload,
                truncate_bytes=128,
                content_length_override=1024,
            ),
        )
        server.add_route(
            "/throttled.bin",
            RouteBehavior(
                body=payload,
                chunk_size=256,
                chunk_delay_seconds=0.01,
                omit_content_length=True,
            ),
        )

        import http.client

        with urllib.request.urlopen(f"{server.url}/truncated.bin", timeout=5) as resp:
            assert resp.headers.get("Content-Length") == "1024"
            with pytest.raises(http.client.IncompleteRead) as inc_exc:
                resp.read()
            assert len(inc_exc.value.partial) == 128

        # Concurrent downloads across multiple threads
        def _fetch_throttled(_: int) -> bytes:
            with urllib.request.urlopen(f"{server.url}/throttled.bin", timeout=5) as r:
                assert r.headers.get("Content-Length") is None
                return bytes(r.read())

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_fetch_throttled, range(4)))

        assert all(res == payload for res in results)


def test_file_route_supports_range_and_etag(tmp_path):
    payload = tmp_path / "range.bin"
    payload.write_bytes(b"0123456789")
    with MockHTTPServer(tmp_path) as server:
        server.add_route(
            "/range.bin",
            RouteBehavior(file_path=payload, accept_ranges=True, etag='"first"'),
        )
        url = f"{server.url}/range.bin"

        def fetch(headers):
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=5
            )

        with fetch({"Range": "bytes=2-5", "If-Range": '"first"'}) as response:
            assert response.status == 206
            assert response.headers["Content-Range"] == "bytes 2-5/10"
            assert response.read() == b"2345"

        with fetch({"Range": "bytes=-3"}) as response:
            assert response.read() == b"789"

        with fetch({"Range": "bytes=2-", "If-Range": '"older"'}) as response:
            assert response.status == 200
            assert response.read() == b"0123456789"

        with pytest.raises(urllib.error.HTTPError) as unsatisfiable:
            fetch({"Range": "bytes=12-"})
        with unsatisfiable.value as response:
            assert response.code == 416
            assert response.headers["Content-Range"] == "bytes */10"

        with pytest.raises(urllib.error.HTTPError) as cached:
            fetch({"If-None-Match": 'W/"first"'})
        with cached.value as response:
            assert response.code == 304
            assert response.read() == b""
