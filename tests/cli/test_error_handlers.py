"""Tests for error handlers in cli/main.py — KeyNotEnrolledError and SessionError."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tescmd.api.errors import KeyNotEnrolledError, SessionError
from tescmd.cli.main import _handle_known_error
from tescmd.output.formatter import OutputFormatter

if TYPE_CHECKING:
    import pytest

# ---------------------------------------------------------------------------
# KeyNotEnrolledError
# ---------------------------------------------------------------------------


class TestHandleKeyNotEnrolledError:
    """Verify _handle_known_error recognises KeyNotEnrolledError."""

    def test_handles_key_not_enrolled(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            KeyNotEnrolledError("not enrolled", status_code=422),
            None,
            formatter,
            "security.lock",
        )
        assert handled is True

    def test_json_output_with_domain(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TESLA_DOMAIN", "testuser.github.io")
        formatter = OutputFormatter(force_format="json")
        _handle_known_error(
            KeyNotEnrolledError("Key not enrolled on vehicle XYZ.", status_code=422),
            None,
            formatter,
            "security.lock",
        )
        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["ok"] is False
        assert output["error"]["code"] == "key_not_enrolled"
        assert "not enrolled" in output["error"]["message"]
        assert "tesla.com/_ak/testuser.github.io" in output["error"]["message"]

    def test_json_output_without_domain(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TESLA_DOMAIN", "")
        formatter = OutputFormatter(force_format="json")
        _handle_known_error(
            KeyNotEnrolledError("not enrolled", status_code=422),
            None,
            formatter,
            "security.lock",
        )
        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["ok"] is False
        assert output["error"]["code"] == "key_not_enrolled"
        # No enrollment URL when domain is not configured
        assert "tesla.com/_ak" not in output["error"]["message"]

    def test_not_confused_with_other_errors(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            RuntimeError("something else"),
            None,
            formatter,
            "security.lock",
        )
        assert handled is False


# ---------------------------------------------------------------------------
# SessionError
# ---------------------------------------------------------------------------


class TestHandleSessionError:
    """Verify _handle_known_error recognises SessionError."""

    def test_handles_session_error(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            SessionError("handshake failed"),
            None,
            formatter,
            "charge.start",
        )
        assert handled is True

    def test_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        formatter = OutputFormatter(force_format="json")
        _handle_known_error(
            SessionError("ECDH handshake timed out"),
            None,
            formatter,
            "charge.start",
        )
        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["ok"] is False
        assert output["error"]["code"] == "session_error"
        assert "ECDH" in output["error"]["message"]
