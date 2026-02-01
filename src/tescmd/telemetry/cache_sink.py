"""Cache-warming telemetry sink.

Receives decoded telemetry frames, translates field values via
:class:`~tescmd.telemetry.mapper.TelemetryMapper`, and merges them into
a :class:`~tescmd.cache.response_cache.ResponseCache`.  This keeps the
MCP tool cache warm so read operations are free while telemetry is active.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tescmd.cache.response_cache import ResponseCache
    from tescmd.telemetry.decoder import TelemetryFrame
    from tescmd.telemetry.mapper import TelemetryMapper

logger = logging.getLogger(__name__)


def _deep_set(target: dict[str, Any], dotted_path: str, value: Any) -> None:
    """Set a value in a nested dict using a dotted path.

    Creates intermediate dicts as needed.

    >>> d: dict[str, Any] = {}
    >>> _deep_set(d, "charge_state.battery_level", 80)
    >>> d
    {'charge_state': {'battery_level': 80}}
    """
    keys = dotted_path.split(".")
    for key in keys[:-1]:
        if key not in target or not isinstance(target[key], dict):
            target[key] = {}
        target = target[key]
    target[keys[-1]] = value


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    """Recursively merge *overlay* into *base* (mutates *base*).

    Dict values are merged recursively; all other values are overwritten.
    """
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


class CacheSink:
    """Telemetry sink that warms the response cache.

    Accumulates telemetry updates in a buffer and flushes them to the
    :class:`ResponseCache` at a configurable interval.  While active,
    cached data is given a generous TTL so MCP reads don't trigger API
    requests.

    Parameters:
        cache: The file-based response cache to write into.
        mapper: Field mapper for telemetry → VehicleData translation.
        vin: Vehicle VIN to cache data for.
        flush_interval: Minimum seconds between disk flushes.
        telemetry_ttl: TTL in seconds for cache entries while streaming.
    """

    def __init__(
        self,
        cache: ResponseCache,
        mapper: TelemetryMapper,
        vin: str,
        *,
        flush_interval: float = 1.0,
        telemetry_ttl: int = 120,
    ) -> None:
        self._cache = cache
        self._mapper = mapper
        self._vin = vin
        self._flush_interval = flush_interval
        self._telemetry_ttl = telemetry_ttl
        self._pending: dict[str, Any] = {}
        self._last_flush: float = 0.0
        self._frame_count: int = 0
        self._field_count: int = 0

    @property
    def frame_count(self) -> int:
        """Total frames processed."""
        return self._frame_count

    @property
    def field_count(self) -> int:
        """Total field updates applied to cache."""
        return self._field_count

    @property
    def pending_count(self) -> int:
        """Number of buffered updates not yet flushed."""
        return self._count_leaves(self._pending)

    async def on_frame(self, frame: TelemetryFrame) -> None:
        """Process a decoded telemetry frame into the cache buffer.

        Skips frames for other VINs. Maps each datum through the
        :class:`TelemetryMapper` and buffers the results for the next
        flush cycle.
        """
        if frame.vin != self._vin:
            return

        self._frame_count += 1

        for datum in frame.data:
            for path, value in self._mapper.map(datum.field_name, datum.value):
                _deep_set(self._pending, path, value)
                self._field_count += 1

        now = time.monotonic()
        if now - self._last_flush >= self._flush_interval:
            self.flush()
            self._last_flush = now

    def flush(self) -> None:
        """Merge buffered updates into the response cache immediately.

        Called automatically during ``on_frame`` when the flush interval
        has elapsed, or manually for cleanup / testing.
        """
        if not self._pending:
            return

        # Read-modify-write: merge into existing cached data
        existing = self._cache.get(self._vin)
        blob: dict[str, Any] = existing.data if existing else {"vin": self._vin, "state": "online"}

        _deep_merge(blob, self._pending)
        self._cache.put(self._vin, blob, ttl=self._telemetry_ttl)
        self._cache.put_wake_state(self._vin, "online", ttl=self._telemetry_ttl)
        self._pending.clear()

        logger.debug("Cache flushed for %s (%d fields)", self._vin, self._field_count)

    @staticmethod
    def _count_leaves(d: dict[str, Any]) -> int:
        """Count leaf (non-dict) values in a nested dict."""
        count = 0
        for v in d.values():
            if isinstance(v, dict):
                count += CacheSink._count_leaves(v)
            else:
                count += 1
        return count
