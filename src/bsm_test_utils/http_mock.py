import http.server
import socketserver
import threading
from pathlib import Path
from typing import Optional


class MockHTTPServer:
    def __init__(self, directory: str, port: int = 0):
        """
        Initializes a mock HTTP server serving files from the given directory.
        :param directory: The root directory to serve files from.
        :param port: The port to bind to. 0 assigns a random available port.
        """
        self.directory = Path(directory)
        self.port = port
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the server in a background thread."""

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, directory=str(self.directory), **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

        self.server = socketserver.TCPServer(("127.0.0.1", self.port), Handler)
        self.port = self.server.server_address[1]  # Update port in case it was 0

        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        """Stops the server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join()

    @property
    def url(self) -> str:
        """Returns the base URL of the server."""
        return f"http://127.0.0.1:{self.port}"
