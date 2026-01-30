"""Tests for tescmd.auth.server — OAuth callback server."""

from __future__ import annotations

import contextlib
import urllib.error
import urllib.request

from tescmd.auth.server import OAuthCallbackServer


class TestOAuthCallbackServer:
    def test_captures_auth_code(self) -> None:
        """Server captures code and state from callback URL."""
        server = OAuthCallbackServer(port=0)  # port=0 lets OS assign free port
        server.start()
        try:
            port = server.server_address[1]
            # Simulate browser redirect
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/callback?code=testcode&state=teststate"
            )
            code, state = server.wait_for_callback(timeout=5)
            assert code == "testcode"
            assert state == "teststate"
        finally:
            server.stop()

    def test_handles_error_callback(self) -> None:
        """Server handles error in callback URL."""
        server = OAuthCallbackServer(port=0)
        server.start()
        try:
            port = server.server_address[1]
            with contextlib.suppress(urllib.error.HTTPError):
                urllib.request.urlopen(f"http://127.0.0.1:{port}/callback?error=access_denied")
            code, state = server.wait_for_callback(timeout=5)
            assert code is None
            assert state is None
        finally:
            server.stop()

    def test_timeout_returns_none(self) -> None:
        """Server returns (None, None) on timeout."""
        server = OAuthCallbackServer(port=0)
        server.start()
        try:
            code, state = server.wait_for_callback(timeout=0.1)
            assert code is None
            assert state is None
        finally:
            server.stop()
