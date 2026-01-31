"""Tests for the partner CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestPartnerHelp:
    def test_partner_help(self) -> None:
        result = CliRunner().invoke(cli, ["partner", "--help"])
        assert result.exit_code == 0
        assert "public-key" in result.output
        assert "telemetry-error-vins" in result.output
        assert "telemetry-errors" in result.output

    def test_partner_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "partner" in result.output


class TestPartnerPublicKey:
    def test_public_key_help(self) -> None:
        result = CliRunner().invoke(cli, ["partner", "public-key", "--help"])
        assert result.exit_code == 0
        assert "--domain" in result.output

    def test_public_key_requires_domain(self) -> None:
        """public-key should fail when --domain is not provided."""
        result = CliRunner().invoke(cli, ["partner", "public-key"])
        assert result.exit_code != 0


class TestPartnerTelemetryErrorVins:
    def test_telemetry_error_vins_help(self) -> None:
        result = CliRunner().invoke(cli, ["partner", "telemetry-error-vins", "--help"])
        assert result.exit_code == 0


class TestPartnerTelemetryErrors:
    def test_telemetry_errors_help(self) -> None:
        result = CliRunner().invoke(cli, ["partner", "telemetry-errors", "--help"])
        assert result.exit_code == 0
