"""Keyring-backed token persistence."""

from __future__ import annotations

import contextlib
import json
from typing import Any

import keyring
from keyring.errors import PasswordDeleteError

SERVICE_NAME = "tescmd"


class TokenStore:
    """Read / write OAuth tokens via the OS keyring."""

    def __init__(self, profile: str = "default") -> None:
        self._profile = profile

    # -- key helpers ---------------------------------------------------------

    def _key(self, name: str) -> str:
        return f"{self._profile}/{name}"

    # -- properties ----------------------------------------------------------

    @property
    def access_token(self) -> str | None:
        """Return the stored access token, or *None*."""
        return keyring.get_password(SERVICE_NAME, self._key("access_token"))

    @property
    def refresh_token(self) -> str | None:
        """Return the stored refresh token, or *None*."""
        return keyring.get_password(SERVICE_NAME, self._key("refresh_token"))

    @property
    def has_token(self) -> bool:
        """Return *True* if an access token is stored."""
        return self.access_token is not None

    @property
    def metadata(self) -> dict[str, Any] | None:
        """Return the parsed metadata dict, or *None*."""
        raw = keyring.get_password(SERVICE_NAME, self._key("metadata"))
        if raw is None:
            return None
        result: dict[str, Any] = json.loads(raw)
        return result

    # -- mutators ------------------------------------------------------------

    def save(
        self,
        access_token: str,
        refresh_token: str,
        expires_at: float,
        scopes: list[str],
        region: str,
    ) -> None:
        """Persist all three keyring entries."""
        keyring.set_password(SERVICE_NAME, self._key("access_token"), access_token)
        keyring.set_password(SERVICE_NAME, self._key("refresh_token"), refresh_token)
        meta = json.dumps({"expires_at": expires_at, "scopes": scopes, "region": region})
        keyring.set_password(SERVICE_NAME, self._key("metadata"), meta)

    def clear(self) -> None:
        """Delete all stored credentials, ignoring missing entries."""
        for name in ("access_token", "refresh_token", "metadata"):
            with contextlib.suppress(PasswordDeleteError):
                keyring.delete_password(SERVICE_NAME, self._key(name))

    # -- import / export -----------------------------------------------------

    def export_dict(self) -> dict[str, Any]:
        """Return a plain dict of all stored values (for ``auth export``)."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "metadata": self.metadata,
        }

    def import_dict(self, data: dict[str, Any]) -> None:
        """Restore tokens from a previously exported dict."""
        meta: dict[str, Any] = data.get("metadata") or {}
        self.save(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=meta.get("expires_at", 0.0),
            scopes=meta.get("scopes", []),
            region=meta.get("region", "na"),
        )
