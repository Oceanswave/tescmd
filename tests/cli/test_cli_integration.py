"""Integration tests for the Click-based CLI."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestCLIHelp:
    def test_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "vehicle" in result.output
        assert "auth" in result.output
        assert "key" in result.output
        assert "setup" in result.output
        assert "charge" in result.output
        assert "climate" in result.output
        assert "security" in result.output
        assert "trunk" in result.output

    def test_no_command_shows_help(self) -> None:
        result = CliRunner().invoke(cli, [])
        assert result.exit_code == 0
        assert "Usage" in result.output

    def test_vehicle_help(self) -> None:
        result = CliRunner().invoke(cli, ["vehicle", "--help"])
        assert result.exit_code == 0
        assert "info" in result.output
        assert "list" in result.output
        assert "data" in result.output
        assert "location" in result.output
        assert "wake" in result.output

    def test_auth_help(self) -> None:
        result = CliRunner().invoke(cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "login" in result.output
        assert "logout" in result.output
        assert "status" in result.output
        assert "refresh" in result.output
        assert "export" in result.output
        assert "register" in result.output
        assert "import" in result.output

    def test_key_help(self) -> None:
        result = CliRunner().invoke(cli, ["key", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.output
        assert "deploy" in result.output
        assert "validate" in result.output
        assert "show" in result.output

    def test_setup_help(self) -> None:
        result = CliRunner().invoke(cli, ["setup", "--help"])
        assert result.exit_code == 0
        assert "wizard" in result.output.lower() or "setup" in result.output.lower()

    def test_charge_help(self) -> None:
        result = CliRunner().invoke(cli, ["charge", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "start" in result.output
        assert "stop" in result.output
        assert "limit" in result.output
        assert "limit-max" in result.output
        assert "limit-std" in result.output
        assert "amps" in result.output
        assert "port-open" in result.output
        assert "port-close" in result.output
        assert "schedule" in result.output

    def test_climate_help(self) -> None:
        result = CliRunner().invoke(cli, ["climate", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "on" in result.output
        assert "off" in result.output
        assert "set" in result.output
        assert "precondition" in result.output
        assert "seat" in result.output
        assert "seat-cool" in result.output
        assert "wheel-heater" in result.output
        assert "overheat" in result.output
        assert "keeper" in result.output

    def test_security_help(self) -> None:
        result = CliRunner().invoke(cli, ["security", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "lock" in result.output
        assert "unlock" in result.output
        assert "sentry" in result.output
        assert "valet" in result.output
        assert "valet-reset" in result.output
        assert "speed-limit" in result.output
        assert "remote-start" in result.output
        assert "flash" in result.output
        assert "honk" in result.output

    def test_trunk_help(self) -> None:
        result = CliRunner().invoke(cli, ["trunk", "--help"])
        assert result.exit_code == 0
        assert "open" in result.output
        assert "close" in result.output
        assert "frunk" in result.output
        assert "window" in result.output


class TestGlobalOptions:
    def test_global_vin_flag_accepted(self) -> None:
        # --vin should be accepted as a global flag without error
        result = CliRunner().invoke(cli, ["--vin", "5YJ3E1EA1NF000001", "--help"])
        assert result.exit_code == 0

    def test_global_format_option(self) -> None:
        result = CliRunner().invoke(cli, ["--format", "json", "--help"])
        assert result.exit_code == 0

    def test_global_quiet_flag(self) -> None:
        result = CliRunner().invoke(cli, ["--quiet", "--help"])
        assert result.exit_code == 0

    def test_global_region_option(self) -> None:
        result = CliRunner().invoke(cli, ["--region", "eu", "--help"])
        assert result.exit_code == 0

    def test_global_verbose_flag(self) -> None:
        result = CliRunner().invoke(cli, ["--verbose", "--help"])
        assert result.exit_code == 0

    def test_global_profile_option(self) -> None:
        result = CliRunner().invoke(cli, ["--profile", "work", "--help"])
        assert result.exit_code == 0

    def test_invalid_format_rejected(self) -> None:
        result = CliRunner().invoke(cli, ["--format", "xml"])
        assert result.exit_code != 0

    def test_invalid_region_rejected(self) -> None:
        result = CliRunner().invoke(cli, ["--region", "jp"])
        assert result.exit_code != 0


class TestCommandLevelGlobalOptions:
    """Global options (--vin, --format, --region, etc.) work after the subcommand."""

    def test_vin_after_vehicle_info(self) -> None:
        result = CliRunner().invoke(
            cli, ["vehicle", "info", "--vin", "5YJ3E1EA1NF000001", "--help"]
        )
        assert result.exit_code == 0

    def test_format_after_vehicle_list(self) -> None:
        result = CliRunner().invoke(cli, ["vehicle", "list", "--format", "json", "--help"])
        assert result.exit_code == 0

    def test_region_after_auth_status(self) -> None:
        result = CliRunner().invoke(cli, ["auth", "status", "--region", "eu", "--help"])
        assert result.exit_code == 0

    def test_quiet_after_key_show(self) -> None:
        result = CliRunner().invoke(cli, ["key", "show", "--quiet", "--help"])
        assert result.exit_code == 0

    def test_verbose_after_setup(self) -> None:
        result = CliRunner().invoke(cli, ["setup", "--verbose", "--help"])
        assert result.exit_code == 0

    def test_profile_after_auth_login(self) -> None:
        result = CliRunner().invoke(cli, ["auth", "login", "--profile", "work", "--help"])
        assert result.exit_code == 0

    def test_invalid_format_rejected_at_command_level(self) -> None:
        result = CliRunner().invoke(cli, ["vehicle", "list", "--format", "xml"])
        assert result.exit_code != 0

    def test_invalid_region_rejected_at_command_level(self) -> None:
        result = CliRunner().invoke(cli, ["auth", "status", "--region", "jp"])
        assert result.exit_code != 0

    def test_multiple_global_options_after_subcommand(self) -> None:
        result = CliRunner().invoke(
            cli,
            ["vehicle", "info", "--vin", "5YJ3E1EA1NF000001", "--format", "json", "--help"],
        )
        assert result.exit_code == 0
