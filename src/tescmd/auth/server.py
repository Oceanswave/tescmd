"""Lightweight local HTTP server for the OAuth2 redirect callback."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

_SUCCESS_HTML = """\
<!DOCTYPE html>
<html><head><title>tescmd</title></head>
<body style="font-family:sans-serif;text-align:center;margin-top:80px">
<h1>Authentication Successful</h1>
<p>You can close this window and return to the terminal.</p>
</body></html>
"""

_FAILURE_HTML = """\
<!DOCTYPE html>
<html><head><title>tescmd</title></head>
<body style="font-family:sans-serif;text-align:center;margin-top:80px">
<h1>Authentication Failed</h1>
<p>{error}</p>
</body></html>
"""


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handle a single GET from the OAuth redirect."""

    server: OAuthCallbackServer

    def do_GET(self) -> None:
        qs = parse_qs(urlparse(self.path).query)

        error = qs.get("error", [None])[0]
        if error is not None:
            self._respond(400, _FAILURE_HTML.format(error=error))
            self.server.callback_result = (None, None, error)
            self.server.callback_event.set()
            return

        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]
        self._respond(200, _SUCCESS_HTML)
        self.server.callback_result = (code, state, None)
        self.server.callback_event.set()

    def _respond(self, status: int, body: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    # Silence default request logging.
    def log_message(self, format: str, *args: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class OAuthCallbackServer(HTTPServer):
    """HTTPServer that waits for a single OAuth redirect callback."""

    def __init__(self, port: int | None = None) -> None:
        if port is None:
            from tescmd.models.auth import DEFAULT_PORT

            port = DEFAULT_PORT
        super().__init__(("127.0.0.1", port), _CallbackHandler)
        self.callback_event = threading.Event()
        self.callback_result: tuple[str | None, str | None, str | None] = (
            None,
            None,
            None,
        )
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start serving in a daemon thread."""
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def wait_for_callback(self, timeout: float = 120) -> tuple[str | None, str | None]:
        """Block until the callback is received or *timeout* elapses.

        Returns ``(code, state)`` on success; ``(None, None)`` on timeout or error.
        """
        received = self.callback_event.wait(timeout=timeout)
        if not received:
            return (None, None)
        code, state, _error = self.callback_result
        return (code, state)

    def stop(self) -> None:
        """Shut down the server and join the daemon thread."""
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
