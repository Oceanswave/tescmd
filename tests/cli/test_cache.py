"""Tests for the cache CLI commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from click.testing import CliRunner

from tescmd.cache.response_cache import ResponseCache
from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pathlib import Path


def _make_cache(tmp_path: Path) -> ResponseCache:
    cache_dir = tmp_path / "cache"
    return ResponseCache(cache_dir=cache_dir, default_ttl=60, enabled=True)


class TestCacheClear:
    def test_clear_empty(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with patch("tescmd.cli.cache.get_cache", return_value=cache):
            result = CliRunner().invoke(cli, ["cache", "clear"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["cleared"] == 0

    def test_clear_with_entries(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        cache.put("VIN_A", {"data": 1})
        cache.put("VIN_B", {"data": 2})
        with patch("tescmd.cli.cache.get_cache", return_value=cache):
            result = CliRunner().invoke(cli, ["cache", "clear"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["cleared"] == 2

    def test_clear_by_vin(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        cache.put("VIN_A", {"data": 1})
        cache.put("VIN_B", {"data": 2})
        with patch("tescmd.cli.cache.get_cache", return_value=cache):
            result = CliRunner().invoke(cli, ["cache", "clear", "--vin", "VIN_A"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["cleared"] == 1
        assert data["data"]["vin"] == "VIN_A"

    def test_clear_json_output(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        cache.put("VIN_A", {"data": 1})
        with patch("tescmd.cli.cache.get_cache", return_value=cache):
            result = CliRunner().invoke(cli, ["--format", "json", "cache", "clear"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["cleared"] == 1


class TestCacheStatus:
    def test_status_empty(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with patch("tescmd.cli.cache.get_cache", return_value=cache):
            result = CliRunner().invoke(cli, ["cache", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["enabled"] is True

    def test_status_with_entries(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        cache.put("VIN_A", {"data": 1})
        with patch("tescmd.cli.cache.get_cache", return_value=cache):
            result = CliRunner().invoke(cli, ["cache", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["total"] == 1

    def test_status_json_output(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with patch("tescmd.cli.cache.get_cache", return_value=cache):
            result = CliRunner().invoke(cli, ["--format", "json", "cache", "status"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "enabled" in data["data"]
        assert "total" in data["data"]


class TestCacheHelp:
    def test_cache_help(self) -> None:
        result = CliRunner().invoke(cli, ["cache", "--help"])
        assert result.exit_code == 0
        assert "clear" in result.output
        assert "status" in result.output

    def test_cache_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "cache" in result.output
