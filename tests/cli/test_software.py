"""Tests for the software CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestSoftwareHelp:
    def test_software_help(self) -> None:
        result = CliRunner().invoke(cli, ["software", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "schedule" in result.output
        assert "cancel" in result.output

    def test_software_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "software" in result.output


class TestSoftwareStatus:
    def test_status_help(self) -> None:
        result = CliRunner().invoke(cli, ["software", "status", "--help"])
        assert result.exit_code == 0
        assert (
            "software version" in result.output.lower() or "update status" in result.output.lower()
        )

    def test_status_accepts_vin_positional(self) -> None:
        result = CliRunner().invoke(cli, ["software", "status", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output


class TestSoftwareSchedule:
    def test_schedule_help(self) -> None:
        result = CliRunner().invoke(cli, ["software", "schedule", "--help"])
        assert result.exit_code == 0
        assert "SECONDS" in result.output

    def test_schedule_requires_seconds(self) -> None:
        """schedule should fail when no seconds argument is provided."""
        result = CliRunner().invoke(cli, ["software", "schedule"])
        assert result.exit_code != 0

    def test_schedule_accepts_vin_positional(self) -> None:
        result = CliRunner().invoke(cli, ["software", "schedule", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output


class TestSoftwareCancel:
    def test_cancel_help(self) -> None:
        result = CliRunner().invoke(cli, ["software", "cancel", "--help"])
        assert result.exit_code == 0
        assert "Cancel" in result.output or "cancel" in result.output.lower()

    def test_cancel_accepts_vin_positional(self) -> None:
        result = CliRunner().invoke(cli, ["software", "cancel", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output
