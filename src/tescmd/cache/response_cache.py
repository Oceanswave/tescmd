"""File-based response cache with per-entry TTL."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tescmd.cache.keys import cache_key

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheResult:
    """Wrapper around cached data that includes freshness metadata."""

    data: dict[str, Any]
    created_at: float
    expires_at: float

    @property
    def age_seconds(self) -> int:
        """Seconds since the data was cached."""
        return int(time.time() - self.created_at)

    @property
    def ttl_seconds(self) -> int:
        """Total TTL that was assigned to this cache entry."""
        return int(self.expires_at - self.created_at)


class ResponseCache:
    """Sync, file-based cache.  Each entry is a JSON file under *cache_dir*.

    Cache files are named ``{vin}_{endpoint_hash}.json`` (data) or
    ``{vin}_wake.json`` (wake state).  The VIN prefix enables per-vehicle
    clearing via glob.
    """

    def __init__(
        self,
        cache_dir: Path,
        default_ttl: int = 60,
        enabled: bool = True,
    ) -> None:
        self._cache_dir = cache_dir
        self._default_ttl = default_ttl
        self._enabled = enabled

    # ------------------------------------------------------------------
    # Vehicle data cache
    # ------------------------------------------------------------------

    def get(self, vin: str, endpoints: list[str] | None = None) -> CacheResult | None:
        """Return cached data with metadata, or ``None`` on miss/expiry."""
        if not self._enabled:
            return None
        path = self._data_path(vin, endpoints)
        return self._read_entry(path)

    def put(
        self,
        vin: str,
        data: dict[str, Any],
        endpoints: list[str] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Store *data* for *vin*/*endpoints* with the given *ttl*."""
        if not self._enabled:
            return
        path = self._data_path(vin, endpoints)
        self._write_entry(path, data, ttl or self._default_ttl)

    # ------------------------------------------------------------------
    # Wake state cache
    # ------------------------------------------------------------------

    def get_wake_state(self, vin: str) -> bool:
        """Return ``True`` if the vehicle was recently confirmed online."""
        if not self._enabled:
            return False
        path = self._wake_path(vin)
        result = self._read_entry(path)
        if result is None:
            return False
        return result.data.get("state") == "online"

    def put_wake_state(self, vin: str, state: str, ttl: int = 30) -> None:
        """Cache the vehicle's wake *state* (e.g. ``"online"``)."""
        if not self._enabled:
            return
        path = self._wake_path(vin)
        self._write_entry(path, {"state": state}, ttl)

    # ------------------------------------------------------------------
    # Generic cache (any scope / endpoint)
    # ------------------------------------------------------------------

    def get_generic(self, key: str) -> CacheResult | None:
        """Return cached data for a pre-computed *key*, or ``None`` on miss/expiry."""
        if not self._enabled:
            return None
        path = self._cache_dir / f"{key}.json"
        return self._read_entry(path)

    def put_generic(self, key: str, data: dict[str, Any], ttl: int | None = None) -> None:
        """Store *data* under a pre-computed *key* with the given *ttl*."""
        if not self._enabled:
            return
        path = self._cache_dir / f"{key}.json"
        self._write_entry(path, data, ttl or self._default_ttl)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear(self, vin: str | None = None) -> int:
        """Delete cache entries.  If *vin* is given, only that vehicle's files.

        Returns the number of files removed.
        """
        if not self._cache_dir.is_dir():
            return 0
        pattern = f"{vin}_*.json" if vin else "*.json"
        removed = 0
        for path in self._cache_dir.glob(pattern):
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def clear_by_prefix(self, prefix: str) -> int:
        """Delete cache entries whose filename starts with *prefix*.

        Returns the number of files removed.  Used for scope-based
        invalidation (e.g. ``clear_by_prefix("site_12345_")``).
        """
        if not self._cache_dir.is_dir():
            return 0
        removed = 0
        for path in self._cache_dir.glob(f"{prefix}*.json"):
            path.unlink(missing_ok=True)
            removed += 1
        return removed

    def status(self) -> dict[str, Any]:
        """Return cache statistics: enabled, dir, ttl, counts, disk usage."""
        result: dict[str, Any] = {
            "enabled": self._enabled,
            "cache_dir": str(self._cache_dir),
            "default_ttl": self._default_ttl,
            "total": 0,
            "fresh": 0,
            "stale": 0,
            "disk_bytes": 0,
        }
        if not self._cache_dir.is_dir():
            return result
        now = time.time()
        for path in self._cache_dir.glob("*.json"):
            result["total"] += 1
            result["disk_bytes"] += path.stat().st_size
            entry = self._read_json(path)
            if entry and entry.get("expires_at", 0) > now:
                result["fresh"] += 1
            else:
                result["stale"] += 1
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _data_path(self, vin: str, endpoints: list[str] | None) -> Path:
        return self._cache_dir / f"{cache_key(vin, endpoints)}.json"

    def _wake_path(self, vin: str) -> Path:
        return self._cache_dir / f"{vin}_wake.json"

    def _read_entry(self, path: Path) -> CacheResult | None:
        """Read and validate a cache entry.  Returns ``None`` if missing or expired."""
        entry = self._read_json(path)
        if entry is None:
            return None
        expires_at = entry.get("expires_at", 0)
        if expires_at <= time.time():
            path.unlink(missing_ok=True)
            return None
        return CacheResult(
            data=entry.get("data", {}),
            created_at=entry.get("created_at", 0.0),
            expires_at=expires_at,
        )

    def _write_entry(self, path: Path, data: dict[str, Any], ttl: int) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        entry = {
            "data": data,
            "created_at": now,
            "expires_at": now + ttl,
        }
        # Atomic write: temp file + rename avoids torn reads.
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry), encoding="utf-8")
        tmp.rename(path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt or unreadable cache file: %s", path)
            return None
