"""Tests for token store backend resolution and fallback logic."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import tescmd.auth.token_store as ts_module
from tescmd.auth.token_store import TokenStore, _resolve_backend

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_warned() -> None:
    """Reset the module-level _warned flag before each test."""
    ts_module._warned = False


# ---------------------------------------------------------------------------
# Keyring available → keyring backend
# ---------------------------------------------------------------------------


class TestKeyringAvailable:
    def test_keyring_backend_when_probe_succeeds(self) -> None:
        with patch("keyring.get_password", return_value=None):
            backend = _resolve_backend()
        assert backend.backend_name == "keyring"

    def test_store_uses_keyring_when_available(self) -> None:
        """TokenStore picks keyring when the probe succeeds."""
        with patch("keyring.get_password", return_value=None):
            store = TokenStore(profile="test")
        assert store.backend_name == "keyring"


# ---------------------------------------------------------------------------
# NoKeyringError → automatic file fallback
# ---------------------------------------------------------------------------


class TestKeyringFallback:
    def test_fallback_on_no_keyring(self, tmp_path: Path) -> None:
        """When keyring raises NoKeyringError, fall back to file backend."""
        from keyring.errors import NoKeyringError

        config_dir = str(tmp_path / "config")
        with (
            patch("keyring.get_password", side_effect=NoKeyringError("no backend")),
            pytest.warns(UserWarning, match="keyring unavailable"),
        ):
            backend = _resolve_backend(config_dir=config_dir)

        assert "file" in backend.backend_name

    def test_fallback_on_generic_runtime_error(self, tmp_path: Path) -> None:
        """Any exception during probe → file fallback."""
        config_dir = str(tmp_path / "config")
        with (
            patch("keyring.get_password", side_effect=RuntimeError("dbus not available")),
            pytest.warns(UserWarning, match="keyring unavailable"),
        ):
            backend = _resolve_backend(config_dir=config_dir)

        assert "file" in backend.backend_name

    def test_fallback_warning_fires_once(self, tmp_path: Path) -> None:
        """The file-fallback warning should only fire once per process."""
        config_dir = str(tmp_path / "config")

        with (
            patch("keyring.get_password", side_effect=RuntimeError("no keyring")),
            pytest.warns(UserWarning, match="keyring unavailable"),
        ):
            _resolve_backend(config_dir=config_dir)

        # Second call should NOT warn
        with (
            patch("keyring.get_password", side_effect=RuntimeError("no keyring")),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("error")  # Would raise if a warning fires
            _resolve_backend(config_dir=config_dir)

    def test_fallback_uses_config_dir(self, tmp_path: Path) -> None:
        """Fallback path should be {config_dir}/tokens.json."""
        config_dir = str(tmp_path / "myconfig")
        with (
            patch("keyring.get_password", side_effect=RuntimeError("no keyring")),
            pytest.warns(UserWarning),
        ):
            backend = _resolve_backend(config_dir=config_dir)

        expected = str(tmp_path / "myconfig" / "tokens.json")
        assert expected in backend.backend_name


# ---------------------------------------------------------------------------
# Explicit token_file → file backend, skips probe entirely
# ---------------------------------------------------------------------------


class TestExplicitTokenFile:
    def test_explicit_file_skips_keyring(self, tmp_path: Path) -> None:
        """When token_file is set, keyring is never probed."""
        token_path = tmp_path / "my_tokens.json"
        # If keyring were probed, this would raise — proving it's skipped
        with patch("keyring.get_password", side_effect=AssertionError("should not probe")):
            store = TokenStore(profile="test", token_file=str(token_path))
        assert "file" in store.backend_name
        assert str(token_path) in store.backend_name

    def test_explicit_file_with_broken_keyring(self, tmp_path: Path) -> None:
        """Explicit token_file should work even if keyring probe would fail."""
        token_path = tmp_path / "tokens.json"
        with patch("keyring.get_password", side_effect=RuntimeError("broken")):
            store = TokenStore(profile="test", token_file=str(token_path))
            store.save("at", "rt", 0.0, [], "na")
            assert store.access_token == "at"

    def test_roundtrip_with_explicit_file(self, tmp_path: Path) -> None:
        """Full save/load cycle with explicit token_file."""
        token_path = tmp_path / "tokens.json"
        store = TokenStore(profile="default", token_file=str(token_path))
        store.save("my_at", "my_rt", 123.0, ["openid"], "eu")

        # New store instance pointing at the same file
        store2 = TokenStore(profile="default", token_file=str(token_path))
        assert store2.access_token == "my_at"
        assert store2.refresh_token == "my_rt"
        meta = store2.metadata
        assert meta is not None
        assert meta["region"] == "eu"
