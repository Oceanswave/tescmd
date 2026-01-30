"""Tests for the nav CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestNavHelp:
    def test_nav_help(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "--help"])
        assert result.exit_code == 0
        assert "send" in result.output
        assert "gps" in result.output
        assert "supercharger" in result.output
        assert "homelink" in result.output
        assert "waypoints" in result.output

    def test_nav_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "nav" in result.output


class TestNavSend:
    def test_send_help(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "send", "--help"])
        assert result.exit_code == 0
        assert "ADDRESS" in result.output
        assert "VIN" in result.output

    def test_send_requires_address(self) -> None:
        """send should fail when no address is provided (even with VIN)."""
        result = CliRunner().invoke(cli, ["nav", "send"])
        assert result.exit_code != 0


class TestNavGps:
    def test_gps_help(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "gps", "--help"])
        assert result.exit_code == 0
        assert "LAT" in result.output
        assert "LON" in result.output
        assert "VIN" in result.output

    def test_gps_requires_coordinates(self) -> None:
        """gps should fail when no coordinates are provided."""
        result = CliRunner().invoke(cli, ["nav", "gps"])
        assert result.exit_code != 0

    def test_gps_requires_both_lat_and_lon(self) -> None:
        """gps should fail when only latitude is provided."""
        result = CliRunner().invoke(cli, ["nav", "gps", "37.7749"])
        assert result.exit_code != 0


class TestNavSupercharger:
    def test_supercharger_help(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "supercharger", "--help"])
        assert result.exit_code == 0
        assert "Supercharger" in result.output

    def test_supercharger_accepts_vin(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "supercharger", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output


class TestNavHomelink:
    def test_homelink_help(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "homelink", "--help"])
        assert result.exit_code == 0
        assert "HomeLink" in result.output or "garage" in result.output.lower()

    def test_homelink_has_lat_lon_options(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "homelink", "--help"])
        assert result.exit_code == 0
        assert "--lat" in result.output
        assert "--lon" in result.output

    def test_homelink_accepts_vin(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "homelink", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output


class TestNavWaypoints:
    def test_waypoints_help(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "waypoints", "--help"])
        assert result.exit_code == 0
        assert "WAYPOINTS_JSON" in result.output

    def test_waypoints_requires_json_arg(self) -> None:
        """waypoints should fail when no JSON argument is provided."""
        result = CliRunner().invoke(cli, ["nav", "waypoints"])
        assert result.exit_code != 0

    def test_waypoints_accepts_vin(self) -> None:
        result = CliRunner().invoke(cli, ["nav", "waypoints", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output
