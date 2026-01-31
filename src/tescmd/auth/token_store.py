"""Token persistence with keyring and file-based backends."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import warnings
from pathlib import Path
from typing import Any, Protocol

SERVICE_NAME = "tescmd"

# Module-level flag so the file-fallback warning fires at most once.
_warned = False


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class _TokenBackend(Protocol):
    """Minimal interface for reading/writing credential entries."""

    @property
    def backend_name(self) -> str: ...
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


# ---------------------------------------------------------------------------
# Keyring backend (delegates to the OS keyring)
# ---------------------------------------------------------------------------


class _KeyringBackend:
    """Wraps the ``keyring`` library."""

    @property
    def backend_name(self) -> str:
        return "keyring"

    def get(self, key: str) -> str | None:
        import keyring as _kr

        return _kr.get_password(SERVICE_NAME, key)

    def set(self, key: str, value: str) -> None:
        import keyring as _kr

        _kr.set_password(SERVICE_NAME, key, value)

    def delete(self, key: str) -> None:
        import keyring as _kr
        from keyring.errors import PasswordDeleteError

        with contextlib.suppress(PasswordDeleteError):
            _kr.delete_password(SERVICE_NAME, key)


# ---------------------------------------------------------------------------
# File backend (JSON file with atomic writes)
# ---------------------------------------------------------------------------


class _FileBackend:
    """Stores credentials in a JSON file at *path*.

    The file is written atomically (write-to-temp + rename) and
    permissions are restricted to the current user.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def backend_name(self) -> str:
        return f"file ({self._path})"

    # -- helpers -------------------------------------------------------------

    def _read_store(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data: dict[str, str] = json.loads(self._path.read_text("utf-8"))
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_store(self, data: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        from tescmd._internal.permissions import secure_file

        # Atomic write: temp file in the same directory → rename
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp", prefix=".tokens_")
        try:
            os.write(fd, json.dumps(data, indent=2).encode("utf-8"))
            os.close(fd)
            fd = -1  # mark as closed
            Path(tmp).replace(self._path)
        except BaseException:
            if fd != -1:
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

        secure_file(self._path)

    # -- interface -----------------------------------------------------------

    def get(self, key: str) -> str | None:
        return self._read_store().get(key)

    def set(self, key: str, value: str) -> None:
        store = self._read_store()
        store[key] = value
        self._write_store(store)

    def delete(self, key: str) -> None:
        store = self._read_store()
        store.pop(key, None)
        self._write_store(store)


# ---------------------------------------------------------------------------
# Backend resolution
# ---------------------------------------------------------------------------


def _resolve_backend(
    token_file: str | None = None,
    config_dir: str | None = None,
) -> _TokenBackend:
    """Choose the best available backend.

    1. Explicit *token_file* → file backend (no keyring probe).
    2. Keyring probe succeeds → keyring backend.
    3. Keyring probe fails → file backend at ``{config_dir}/tokens.json``
       with a one-time warning.
    """
    # 1. Explicit token file — skip keyring entirely
    if token_file:
        return _FileBackend(Path(token_file).expanduser())

    # 2. Probe keyring
    try:
        import keyring as _kr

        _kr.get_password(SERVICE_NAME, "__probe__")
        return _KeyringBackend()
    except Exception:
        # NoKeyringError, RuntimeError, or any other keyring failure
        pass

    # 3. Fall back to file
    global _warned
    resolved_dir = Path(config_dir or "~/.config/tescmd").expanduser()
    fallback_path = resolved_dir / "tokens.json"
    if not _warned:
        _warned = True
        warnings.warn(
            f"OS keyring unavailable — storing tokens in {fallback_path} "
            "(plaintext with restricted permissions). "
            "Set TESLA_TOKEN_FILE to choose a different path.",
            UserWarning,
            stacklevel=3,
        )
    return _FileBackend(fallback_path)


# ---------------------------------------------------------------------------
# Public API (unchanged surface)
# ---------------------------------------------------------------------------


class TokenStore:
    """Read / write OAuth tokens via the OS keyring or a file fallback."""

    def __init__(
        self,
        profile: str = "default",
        *,
        token_file: str | None = None,
        config_dir: str | None = None,
    ) -> None:
        self._profile = profile
        self._backend: _TokenBackend = _resolve_backend(token_file, config_dir)

    # -- key helpers ---------------------------------------------------------

    def _key(self, name: str) -> str:
        return f"{self._profile}/{name}"

    # -- diagnostics ---------------------------------------------------------

    @property
    def backend_name(self) -> str:
        """Return a human-readable description of the active backend."""
        return self._backend.backend_name

    # -- properties ----------------------------------------------------------

    @property
    def access_token(self) -> str | None:
        """Return the stored access token, or *None*."""
        return self._backend.get(self._key("access_token"))

    @property
    def refresh_token(self) -> str | None:
        """Return the stored refresh token, or *None*."""
        return self._backend.get(self._key("refresh_token"))

    @property
    def has_token(self) -> bool:
        """Return *True* if an access token is stored."""
        return self.access_token is not None

    @property
    def metadata(self) -> dict[str, Any] | None:
        """Return the parsed metadata dict, or *None*."""
        raw = self._backend.get(self._key("metadata"))
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
        """Persist all three entries."""
        self._backend.set(self._key("access_token"), access_token)
        self._backend.set(self._key("refresh_token"), refresh_token)
        meta = json.dumps({"expires_at": expires_at, "scopes": scopes, "region": region})
        self._backend.set(self._key("metadata"), meta)

    def clear(self) -> None:
        """Delete all stored credentials."""
        for name in ("access_token", "refresh_token", "metadata"):
            self._backend.delete(self._key(name))

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
