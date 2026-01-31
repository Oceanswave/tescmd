"""Tests for the status CLI command."""

from __future__ import annotations

import json
import time
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


_SETTINGS_DEFAULTS = {
    "client_id": "abc12345xyz",
    "client_secret": "secret",
    "domain": "example.com",
    "vin": "5YJ3E1EA1NF000001",
    "region": "na",
    "config_dir": "~/.config/tescmd",
    "cache_dir": "~/.cache/tescmd",
    "cache_enabled": True,
    "cache_ttl": 60,
    "setup_tier": "full",
    "access_token": None,
    "refresh_token": None,
    "token_file": None,
    "output_format": None,
    "profile": "default",
    "github_repo": None,
}


def _patch_settings(**overrides: object) -> patch:
    """Return a patch for AppSettings that returns a mock with given attributes."""
    values = {**_SETTINGS_DEFAULTS, **overrides}

    class FakeSettings:
        def __getattr__(self, name: str) -> object:
            if name in values:
                return values[name]
            raise AttributeError(name)

    return patch("tescmd.cli.status.AppSettings", return_value=FakeSettings())


def _patch_token_store(
    has_token: bool = False,
    metadata: dict | None = None,
    refresh_token: str | None = None,
) -> patch:
    """Return a patch for TokenStore."""

    class FakeTokenStore:
        def __init__(self, profile: str = "default") -> None:
            pass

        @property
        def has_token(self) -> bool:
            return has_token

        @property
        def metadata(self) -> dict | None:
            return metadata

        @property
        def refresh_token(self) -> str | None:
            return refresh_token

    return patch("tescmd.cli.status.TokenStore", return_value=FakeTokenStore())


class TestStatusJsonOutput:
    def test_json_has_all_expected_keys(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        expected_keys = {
            "profile",
            "region",
            "vin",
            "setup_tier",
            "domain",
            "client_id",
            "authenticated",
            "expires_in",
            "has_refresh_token",
            "cache_enabled",
            "cache_ttl",
            "cache_entries",
            "cache_fresh",
            "cache_stale",
            "config_dir",
            "cache_dir",
            "key_pairs",
        }
        assert expected_keys <= set(data.keys())

    def test_command_field(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        envelope = json.loads(result.output)
        assert envelope["command"] == "status"


class TestStatusAuthenticated:
    def test_authenticated_true(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        expires_at = time.time() + 3600
        with (
            _patch_settings(),
            _patch_token_store(
                has_token=True,
                metadata={"expires_at": expires_at, "scopes": [], "region": "na"},
                refresh_token="rt_abc",
            ),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["authenticated"] is True
        assert data["expires_in"] > 0
        assert data["has_refresh_token"] is True

    def test_not_authenticated(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(),
            _patch_token_store(has_token=False),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["authenticated"] is False
        assert data["expires_in"] is None
        assert data["has_refresh_token"] is False


class TestStatusRichOutput:
    def test_rich_exit_code(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["--format", "rich", "status"])
        assert result.exit_code == 0


class TestStatusShowsProfile:
    def test_profile_in_output(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["profile"] == "default"


class TestStatusShowsCacheInfo:
    def test_cache_entries_in_output(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        cache.put("VIN_A", {"charge_state": {"battery_level": 72}})
        cache.put("VIN_B", {"charge_state": {"battery_level": 55}})
        with (
            _patch_settings(),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["cache_entries"] == 2
        assert data["cache_ttl"] == 60
        assert data["cache_enabled"] is True


class TestStatusMasksClientId:
    def test_client_id_truncated(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(client_id="abc12345xyz_long_id"),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["client_id"] == "abc12345\u2026"

    def test_short_client_id_not_truncated(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(client_id="short"),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["client_id"] == "short"

    def test_no_client_id(self, tmp_path: Path) -> None:
        cache = _make_cache(tmp_path)
        with (
            _patch_settings(client_id=None),
            _patch_token_store(),
            patch("tescmd.cli.status.get_cache", return_value=cache),
        ):
            result = CliRunner().invoke(cli, ["status"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["client_id"] == "not set"
