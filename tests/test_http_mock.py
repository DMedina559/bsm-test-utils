import urllib.request

from bsm_test_utils.http_mock import MockHTTPServer


def test_mock_http_server(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    server = MockHTTPServer(directory=str(tmp_path))
    server.start()

    try:
        url = f"{server.url}/test.txt"
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            assert response.read().decode("utf-8") == "hello world"
    finally:
        server.stop()
