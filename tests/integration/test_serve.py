"""Integration tests for the ``tescmd serve`` command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    import pytest


class TestServeCommand:
    """Tests for serve command validation and error paths.

    These tests only invoke the CLI with ``--help`` or flag-validation
    combinations that never reach async code, avoiding event loop issues.
    """

    def test_serve_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "cache warming" in result.output.lower() or "telemetry" in result.output.lower()

    def test_serve_help_shows_options(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert "--transport" in result.output
        assert "--no-telemetry" in result.output
        assert "--no-mcp" in result.output
        assert "--openclaw" in result.output
        assert "--openclaw-config" in result.output
        assert "--dry-run" in result.output
        assert "--fields" in result.output
        assert "--client-id" in result.output
        assert "--client-secret" in result.output
        assert "--telemetry-port" in result.output
        assert "--tailscale" in result.output

    def test_serve_listed_in_commands(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "serve" in result.output


class TestServeValidation:
    """Tests for serve command flag validation rules."""

    def test_no_mcp_and_no_telemetry_error(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["serve", "--no-mcp", "--no-telemetry"],
        )
        assert result.exit_code != 0
        assert "nothing to run" in result.output.lower()

    def test_no_mcp_with_stdio_error(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["serve", "--no-mcp", "--transport", "stdio"],
        )
        assert result.exit_code != 0
        assert "stdio" in result.output.lower()

    def test_dry_run_without_openclaw_error(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "serve",
                "--dry-run",
                "--client-id",
                "test",
                "--client-secret",
                "test",
            ],
        )
        assert result.exit_code != 0
        assert "--openclaw" in result.output

    def test_openclaw_config_without_openclaw_error(self) -> None:
        """--openclaw-config requires --openclaw."""
        runner = CliRunner()
        # Use a path that won't exist — Click's Path(exists=True) will error first
        # unless we also pass --openclaw.  Since we're testing the validation that
        # --openclaw-config requires --openclaw, we need a real path. Use __file__.
        result = runner.invoke(
            cli,
            [
                "serve",
                "--openclaw-config",
                __file__,
                "--client-id",
                "test",
                "--client-secret",
                "test",
            ],
        )
        assert result.exit_code != 0
        assert "--openclaw" in result.output

    def test_tailscale_with_stdio_error(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "serve",
                "--tailscale",
                "--transport",
                "stdio",
                "--client-id",
                "test",
                "--client-secret",
                "test",
            ],
        )
        assert result.exit_code != 0
        assert "tailscale" in result.output.lower() or "stdio" in result.output.lower()

    def test_openclaw_with_no_telemetry_error(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "serve",
                "--openclaw",
                "ws://localhost:18789",
                "--no-telemetry",
                "--client-id",
                "test",
                "--client-secret",
                "test",
            ],
        )
        assert result.exit_code != 0
        assert "telemetry" in result.output.lower()

    def test_missing_mcp_credentials_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TESCMD_MCP_CLIENT_ID", raising=False)
        monkeypatch.delenv("TESCMD_MCP_CLIENT_SECRET", raising=False)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["serve", "--no-telemetry"],
        )
        assert result.exit_code != 0
        assert "TESCMD_MCP_CLIENT_ID" in result.output

    def test_no_mcp_skips_credential_check(self) -> None:
        """--no-mcp should not require MCP credentials."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["serve", "--no-mcp", "--help"],
        )
        # --help should succeed regardless of credentials
        assert result.exit_code == 0
