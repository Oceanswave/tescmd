"""Tests for main() error handling and CLI entry point."""

from __future__ import annotations

import pytest

from tescmd.api.errors import AuthError, RegistrationRequiredError, VehicleAsleepError
from tescmd.cli.main import _handle_known_error, main
from tescmd.output.formatter import OutputFormatter


class TestMainErrorHandling:
    def test_invalid_command_exits_nonzero(self) -> None:
        """Unknown command causes non-zero exit."""
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent-command"])
        assert exc_info.value.code != 0

    def test_help_returns_normally(self) -> None:
        """--help flag returns without raising (standalone_mode=False)."""
        # With standalone_mode=False, --help prints output and returns None
        # rather than raising SystemExit.
        result = main(["--help"])
        assert result is None

    def test_no_args_returns_normally(self) -> None:
        """Running with no args shows help and returns without raising."""
        result = main([])
        assert result is None


class TestHandleKnownError:
    def test_handles_auth_error(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            AuthError("Token expired", status_code=401),
            None,
            formatter,
            "test.cmd",
        )
        assert handled is True

    def test_handles_vehicle_asleep_error(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            VehicleAsleepError("Vehicle is asleep", status_code=408),
            None,
            formatter,
            "test.cmd",
        )
        assert handled is True

    def test_handles_registration_required_error(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            RegistrationRequiredError("Not registered", status_code=412),
            None,
            formatter,
            "test.cmd",
        )
        assert handled is True

    def test_does_not_handle_unknown_error(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            RuntimeError("unknown"),
            None,
            formatter,
            "test.cmd",
        )
        assert handled is False
