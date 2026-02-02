"""Tests for the telemetry stream CLI command."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestStreamHelp:
    def test_help_output(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["vehicle", "telemetry", "stream", "--help"])
        assert result.exit_code == 0
        assert "Stream real-time telemetry" in result.output
        assert "--port" in result.output
        assert "--fields" in result.output
        assert "--interval" in result.output
        assert "--no-log" in result.output
        assert "--legacy-dashboard" in result.output


class TestStreamTailscaleNotInstalled:
    def test_exits_with_error_when_tailscale_missing(self, cli_env: dict[str, str]) -> None:
        """When tailscale is not on PATH, raises TailscaleError."""
        from unittest.mock import patch

        from tescmd.api.errors import TailscaleError

        with patch("tescmd.telemetry.tailscale.shutil.which", return_value=None):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "--format",
                    "json",
                    "vehicle",
                    "telemetry",
                    "stream",
                ],
            )
            assert result.exit_code != 0
            assert result.exception is not None
            assert isinstance(result.exception, (TailscaleError, SystemExit))
