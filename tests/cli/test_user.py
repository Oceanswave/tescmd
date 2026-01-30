"""Tests for the user CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestUserHelp:
    def test_user_help(self) -> None:
        result = CliRunner().invoke(cli, ["user", "--help"])
        assert result.exit_code == 0
        assert "me" in result.output
        assert "region" in result.output
        assert "orders" in result.output
        assert "features" in result.output

    def test_user_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "user" in result.output


class TestUserMe:
    def test_me_help(self) -> None:
        result = CliRunner().invoke(cli, ["user", "me", "--help"])
        assert result.exit_code == 0
        assert "account" in result.output.lower() or "information" in result.output.lower()


class TestUserRegion:
    def test_region_help(self) -> None:
        result = CliRunner().invoke(cli, ["user", "region", "--help"])
        assert result.exit_code == 0
        assert "region" in result.output.lower() or "Fleet API" in result.output


class TestUserOrders:
    def test_orders_help(self) -> None:
        result = CliRunner().invoke(cli, ["user", "orders", "--help"])
        assert result.exit_code == 0
        assert "order" in result.output.lower()


class TestUserFeatures:
    def test_features_help(self) -> None:
        result = CliRunner().invoke(cli, ["user", "features", "--help"])
        assert result.exit_code == 0
        assert "feature" in result.output.lower()
