"""Tests for the energy CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestEnergyHelp:
    def test_energy_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "status" in result.output
        assert "live" in result.output
        assert "backup" in result.output
        assert "mode" in result.output
        assert "storm" in result.output
        assert "tou" in result.output
        assert "history" in result.output
        assert "off-grid" in result.output
        assert "grid-config" in result.output
        assert "calendar" in result.output

    def test_energy_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "energy" in result.output


class TestEnergyList:
    def test_list_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "list", "--help"])
        assert result.exit_code == 0
        assert "energy products" in result.output.lower() or "Powerwall" in result.output


class TestEnergyStatus:
    def test_status_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "status", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output

    def test_status_requires_site_id(self) -> None:
        """status should fail when no site_id is provided."""
        result = CliRunner().invoke(cli, ["energy", "status"])
        assert result.exit_code != 0


class TestEnergyLive:
    def test_live_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "live", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output

    def test_live_requires_site_id(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "live"])
        assert result.exit_code != 0


class TestEnergyBackup:
    def test_backup_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "backup", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output
        assert "PERCENT" in result.output

    def test_backup_requires_args(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "backup"])
        assert result.exit_code != 0


class TestEnergyMode:
    def test_mode_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "mode", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output
        assert "self_consumption" in result.output
        assert "backup" in result.output
        assert "autonomous" in result.output

    def test_mode_requires_args(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "mode"])
        assert result.exit_code != 0


class TestEnergyStorm:
    def test_storm_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "storm", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output
        assert "--on" in result.output or "--off" in result.output

    def test_storm_requires_site_id(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "storm"])
        assert result.exit_code != 0


class TestEnergyTou:
    def test_tou_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "tou", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output
        assert "SETTINGS_JSON" in result.output

    def test_tou_requires_args(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "tou"])
        assert result.exit_code != 0


class TestEnergyHistory:
    def test_history_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "history", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output

    def test_history_requires_site_id(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "history"])
        assert result.exit_code != 0


class TestEnergyOffGrid:
    def test_off_grid_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "off-grid", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output
        assert "RESERVE" in result.output

    def test_off_grid_requires_args(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "off-grid"])
        assert result.exit_code != 0


class TestEnergyGridConfig:
    def test_grid_config_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "grid-config", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output
        assert "CONFIG_JSON" in result.output

    def test_grid_config_requires_args(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "grid-config"])
        assert result.exit_code != 0


class TestEnergyCalendar:
    def test_calendar_help(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "calendar", "--help"])
        assert result.exit_code == 0
        assert "SITE_ID" in result.output

    def test_calendar_has_kind_option(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "calendar", "--help"])
        assert result.exit_code == 0
        assert "--kind" in result.output
        assert "energy" in result.output
        assert "backup" in result.output

    def test_calendar_has_period_option(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "calendar", "--help"])
        assert result.exit_code == 0
        assert "--period" in result.output
        assert "day" in result.output

    def test_calendar_has_date_options(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "calendar", "--help"])
        assert result.exit_code == 0
        assert "--start-date" in result.output
        assert "--end-date" in result.output

    def test_calendar_requires_site_id(self) -> None:
        result = CliRunner().invoke(cli, ["energy", "calendar"])
        assert result.exit_code != 0
