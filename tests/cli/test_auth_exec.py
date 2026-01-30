"""Execution tests for the auth CLI commands.

These tests exercise auth subcommands that do NOT require a real browser or
OAuth flow.  The ``TokenStore`` is mocked so no OS keyring interaction occurs.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from tescmd.cli.main import cli

# ---------------------------------------------------------------------------
# auth status
# ---------------------------------------------------------------------------


class TestAuthStatus:
    def test_status_not_logged_in(self, cli_env: dict[str, str]) -> None:
        """auth status reports authenticated=false when no token is stored."""
        mock_store = MagicMock()
        mock_store.has_token = False

        with patch("tescmd.cli.auth.TokenStore", return_value=mock_store):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["--format", "json", "auth", "status"], catch_exceptions=False
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "auth.status"
        assert parsed["data"]["authenticated"] is False

    def test_status_logged_in(self, cli_env: dict[str, str]) -> None:
        """auth status returns full details when a valid token exists."""
        mock_store = MagicMock()
        mock_store.has_token = True
        mock_store.refresh_token = "rt-test-refresh"
        mock_store.metadata = {
            "expires_at": time.time() + 3600,
            "scopes": ["openid", "vehicle_device_data"],
            "region": "na",
        }

        with patch("tescmd.cli.auth.TokenStore", return_value=mock_store):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["--format", "json", "auth", "status"], catch_exceptions=False
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "auth.status"

        data = parsed["data"]
        assert data["authenticated"] is True
        assert data["has_refresh_token"] is True
        assert data["region"] == "na"
        assert data["scopes"] == ["openid", "vehicle_device_data"]
        assert data["expires_in"] > 0

    def test_status_logged_in_no_refresh_token(self, cli_env: dict[str, str]) -> None:
        """auth status correctly reports has_refresh_token=false."""
        mock_store = MagicMock()
        mock_store.has_token = True
        mock_store.refresh_token = None
        mock_store.metadata = {
            "expires_at": time.time() + 1800,
            "scopes": ["openid"],
            "region": "eu",
        }

        with patch("tescmd.cli.auth.TokenStore", return_value=mock_store):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["--format", "json", "auth", "status"], catch_exceptions=False
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        data = parsed["data"]
        assert data["authenticated"] is True
        assert data["has_refresh_token"] is False
        assert data["region"] == "eu"

    def test_status_expired_token_shows_zero(self, cli_env: dict[str, str]) -> None:
        """auth status clamps expires_in to 0 when token is already expired."""
        mock_store = MagicMock()
        mock_store.has_token = True
        mock_store.refresh_token = "rt-old"
        mock_store.metadata = {
            "expires_at": time.time() - 600,  # expired 10 minutes ago
            "scopes": [],
            "region": "na",
        }

        with patch("tescmd.cli.auth.TokenStore", return_value=mock_store):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["--format", "json", "auth", "status"], catch_exceptions=False
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["data"]["authenticated"] is True
        assert parsed["data"]["expires_in"] == 0


# ---------------------------------------------------------------------------
# auth logout
# ---------------------------------------------------------------------------


class TestAuthLogout:
    def test_logout_clears_tokens(self, cli_env: dict[str, str]) -> None:
        """auth logout calls store.clear() and reports logged_out."""
        mock_store = MagicMock()

        with patch("tescmd.cli.auth.TokenStore", return_value=mock_store):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["--format", "json", "auth", "logout"], catch_exceptions=False
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "auth.logout"
        assert parsed["data"]["status"] == "logged_out"
        mock_store.clear.assert_called_once()


# ---------------------------------------------------------------------------
# auth export
# ---------------------------------------------------------------------------


class TestAuthExport:
    def test_export_outputs_token_json(self, cli_env: dict[str, str]) -> None:
        """auth export prints raw token data as JSON (no envelope)."""
        mock_store = MagicMock()
        mock_store.export_dict.return_value = {
            "access_token": "at-test-access",
            "refresh_token": "rt-test-refresh",
            "metadata": {
                "expires_at": 1700000000.0,
                "scopes": ["openid", "vehicle_device_data"],
                "region": "na",
            },
        }

        with patch("tescmd.cli.auth.TokenStore", return_value=mock_store):
            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "export"], catch_exceptions=False)

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        # auth export uses print() directly -- no envelope wrapper
        assert parsed["access_token"] == "at-test-access"
        assert parsed["refresh_token"] == "rt-test-refresh"
        assert parsed["metadata"]["region"] == "na"
        mock_store.export_dict.assert_called_once()

    def test_export_empty_store(self, cli_env: dict[str, str]) -> None:
        """auth export outputs nulls when no tokens are stored."""
        mock_store = MagicMock()
        mock_store.export_dict.return_value = {
            "access_token": None,
            "refresh_token": None,
            "metadata": None,
        }

        with patch("tescmd.cli.auth.TokenStore", return_value=mock_store):
            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "export"], catch_exceptions=False)

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["access_token"] is None
        assert parsed["refresh_token"] is None
        assert parsed["metadata"] is None
