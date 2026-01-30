"""Tests for the raw CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestRawHelp:
    def test_raw_help(self) -> None:
        result = CliRunner().invoke(cli, ["raw", "--help"])
        assert result.exit_code == 0
        assert "get" in result.output
        assert "post" in result.output

    def test_raw_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "raw" in result.output


class TestRawGet:
    def test_get_help(self) -> None:
        result = CliRunner().invoke(cli, ["raw", "get", "--help"])
        assert result.exit_code == 0
        assert "PATH" in result.output

    def test_get_requires_path(self) -> None:
        """get should fail when no path is provided."""
        result = CliRunner().invoke(cli, ["raw", "get"])
        assert result.exit_code != 0

    def test_get_has_params_option(self) -> None:
        result = CliRunner().invoke(cli, ["raw", "get", "--help"])
        assert result.exit_code == 0
        assert "--params" in result.output

    def test_get_help_shows_example(self) -> None:
        result = CliRunner().invoke(cli, ["raw", "get", "--help"])
        assert result.exit_code == 0
        assert "GET" in result.output or "raw" in result.output.lower()


class TestRawPost:
    def test_post_help(self) -> None:
        result = CliRunner().invoke(cli, ["raw", "post", "--help"])
        assert result.exit_code == 0
        assert "PATH" in result.output

    def test_post_requires_path(self) -> None:
        """post should fail when no path is provided."""
        result = CliRunner().invoke(cli, ["raw", "post"])
        assert result.exit_code != 0

    def test_post_has_body_option(self) -> None:
        result = CliRunner().invoke(cli, ["raw", "post", "--help"])
        assert result.exit_code == 0
        assert "--body" in result.output

    def test_post_help_shows_example(self) -> None:
        result = CliRunner().invoke(cli, ["raw", "post", "--help"])
        assert result.exit_code == 0
        assert "POST" in result.output or "raw" in result.output.lower()
