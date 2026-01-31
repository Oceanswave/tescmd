"""Tests for the file-based token backend."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from tescmd.auth.token_store import TokenStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def token_file(tmp_path: Path) -> Path:
    return tmp_path / "tokens.json"


@pytest.fixture
def store(token_file: Path) -> TokenStore:
    return TokenStore(profile="test", token_file=str(token_file))


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------


class TestFileBackendRoundtrip:
    def test_save_and_load(self, store: TokenStore) -> None:
        store.save(
            access_token="at_123",
            refresh_token="rt_456",
            expires_at=1700000000.0,
            scopes=["openid", "vehicle_device_data"],
            region="eu",
        )
        assert store.access_token == "at_123"
        assert store.refresh_token == "rt_456"
        meta = store.metadata
        assert meta is not None
        assert meta["region"] == "eu"
        assert meta["scopes"] == ["openid", "vehicle_device_data"]

    def test_has_token(self, store: TokenStore) -> None:
        assert store.has_token is False
        store.save("at", "rt", 0.0, [], "na")
        assert store.has_token is True

    def test_clear(self, store: TokenStore) -> None:
        store.save("at", "rt", 0.0, [], "na")
        store.clear()
        assert store.access_token is None
        assert store.refresh_token is None
        assert store.metadata is None

    def test_export_import(self, store: TokenStore) -> None:
        store.save("at", "rt", 99.0, ["s1"], "na")
        data = store.export_dict()
        store.clear()
        assert store.has_token is False
        store.import_dict(data)
        assert store.access_token == "at"
        assert store.refresh_token == "rt"


# ---------------------------------------------------------------------------
# Parent directory creation
# ---------------------------------------------------------------------------


class TestParentDirCreation:
    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "tokens.json"
        store = TokenStore(profile="test", token_file=str(deep))
        store.save("at", "rt", 0.0, [], "na")
        assert deep.exists()


# ---------------------------------------------------------------------------
# File permissions (Unix only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions only")
class TestFilePermissions:
    def test_file_is_0600(self, store: TokenStore, token_file: Path) -> None:
        store.save("at", "rt", 0.0, [], "na")
        mode = token_file.stat().st_mode & 0o777
        assert mode == 0o600


# ---------------------------------------------------------------------------
# Corrupted JSON
# ---------------------------------------------------------------------------


class TestCorruptedJson:
    def test_corrupted_json_returns_none(self, token_file: Path) -> None:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text("{invalid json!!!", encoding="utf-8")
        store = TokenStore(profile="test", token_file=str(token_file))
        assert store.access_token is None

    def test_empty_file_returns_none(self, token_file: Path) -> None:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text("", encoding="utf-8")
        store = TokenStore(profile="test", token_file=str(token_file))
        assert store.access_token is None


# ---------------------------------------------------------------------------
# Multiple profiles in same file
# ---------------------------------------------------------------------------


class TestMultipleProfiles:
    def test_profiles_are_isolated(self, token_file: Path) -> None:
        store_a = TokenStore(profile="alpha", token_file=str(token_file))
        store_b = TokenStore(profile="beta", token_file=str(token_file))

        store_a.save("at_a", "rt_a", 0.0, [], "na")
        store_b.save("at_b", "rt_b", 0.0, [], "eu")

        assert store_a.access_token == "at_a"
        assert store_b.access_token == "at_b"

        store_a.clear()
        assert store_a.access_token is None
        assert store_b.access_token == "at_b"


# ---------------------------------------------------------------------------
# Atomic write (no .tmp residue on success)
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_no_tmp_residue(self, store: TokenStore, token_file: Path) -> None:
        store.save("at", "rt", 0.0, [], "na")
        parent = token_file.parent
        tmp_files = [f for f in parent.iterdir() if f.suffix == ".tmp"]
        assert tmp_files == []


# ---------------------------------------------------------------------------
# Backend name
# ---------------------------------------------------------------------------


class TestBackendName:
    def test_backend_name_contains_path(self, store: TokenStore, token_file: Path) -> None:
        assert "file" in store.backend_name
        assert str(token_file) in store.backend_name
