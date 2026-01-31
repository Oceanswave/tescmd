"""Tests for tescmd.auth.token_store — keyring-backed token persistence."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tescmd.auth.token_store import TokenStore, _KeyringBackend

# ---------------------------------------------------------------------------
# Dict-backed mock keyring
# ---------------------------------------------------------------------------


class _MockKeyring:
    """In-memory keyring replacement."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        from keyring.errors import PasswordDeleteError

        if (service, username) not in self._store:
            raise PasswordDeleteError(username)
        del self._store[(service, username)]


@pytest.fixture
def mock_kr() -> _MockKeyring:
    return _MockKeyring()


@pytest.fixture
def store(mock_kr: _MockKeyring) -> TokenStore:
    """Build a TokenStore that uses the keyring backend with mocked keyring."""
    with (
        patch("keyring.get_password", mock_kr.get_password),
        patch("keyring.set_password", mock_kr.set_password),
        patch("keyring.delete_password", mock_kr.delete_password),
        patch(
            "tescmd.auth.token_store._resolve_backend",
            return_value=_KeyringBackend(),
        ),
    ):
        yield TokenStore(profile="test")  # type: ignore[misc]


class TestSaveAndLoadTokens:
    def test_save_and_load_tokens(self, mock_kr: _MockKeyring, store: TokenStore) -> None:
        with (
            patch("keyring.get_password", mock_kr.get_password),
            patch("keyring.set_password", mock_kr.set_password),
            patch("keyring.delete_password", mock_kr.delete_password),
        ):
            store.save(
                access_token="at",
                refresh_token="rt",
                expires_at=1700000000.0,
                scopes=["openid"],
                region="na",
            )
            assert store.access_token == "at"
            assert store.refresh_token == "rt"
            meta = store.metadata
            assert meta is not None
            assert meta["region"] == "na"


class TestLoadMissingToken:
    def test_load_missing_token(self, mock_kr: _MockKeyring, store: TokenStore) -> None:
        with patch("keyring.get_password", mock_kr.get_password):
            assert store.access_token is None


class TestClearTokens:
    def test_clear_tokens(self, mock_kr: _MockKeyring, store: TokenStore) -> None:
        with (
            patch("keyring.get_password", mock_kr.get_password),
            patch("keyring.set_password", mock_kr.set_password),
            patch("keyring.delete_password", mock_kr.delete_password),
        ):
            store.save(
                access_token="at",
                refresh_token="rt",
                expires_at=0.0,
                scopes=[],
                region="na",
            )
            store.clear()
            assert store.access_token is None


class TestHasToken:
    def test_has_token(self, mock_kr: _MockKeyring, store: TokenStore) -> None:
        with (
            patch("keyring.get_password", mock_kr.get_password),
            patch("keyring.set_password", mock_kr.set_password),
        ):
            assert store.has_token is False
            store.save(
                access_token="at",
                refresh_token="rt",
                expires_at=0.0,
                scopes=[],
                region="na",
            )
            assert store.has_token is True
