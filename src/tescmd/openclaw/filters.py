"""Dual-gate filter for telemetry field emission.

Both conditions must pass for a field to be emitted:

1. **Delta gate** — the value has changed beyond a field-specific granularity
   threshold since the last emitted value.
2. **Throttle gate** — enough time has elapsed since the last emission.

Fields with ``granularity=0`` emit on any value change (state fields like
``ChargeState``, ``Locked``).  Fields with ``throttle_seconds=0`` have no
time constraint.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tescmd.openclaw.config import FieldFilter


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters between two WGS-84 coordinates.

    Pure stdlib implementation — no external dependencies.
    """
    r = 6_371_000.0  # Earth radius in meters
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _numeric_delta(old: Any, new: Any) -> float:
    """Absolute difference between two numeric values."""
    try:
        return abs(float(new) - float(old))
    except (TypeError, ValueError):
        # Non-numeric — treat as changed
        return float("inf")


def _location_delta(old: Any, new: Any) -> float:
    """Distance in meters between two location values.

    Location values are expected as ``{"latitude": float, "longitude": float}``.
    """
    try:
        return haversine(
            old["latitude"],
            old["longitude"],
            new["latitude"],
            new["longitude"],
        )
    except (TypeError, KeyError, ValueError):
        return float("inf")


# Fields that use location-based delta comparison
_LOCATION_FIELDS: frozenset[str] = frozenset({"Location"})


class DualGateFilter:
    """Dual-gate emission filter combining delta + throttle logic.

    Usage::

        filt = DualGateFilter(field_filters)
        if filt.should_emit("Soc", 72, time.monotonic()):
            filt.record_emit("Soc", 72, time.monotonic())
            # ... emit the event
    """

    def __init__(self, filters: dict[str, FieldFilter]) -> None:
        self._filters = filters
        self._last_values: dict[str, Any] = {}
        self._last_emit_times: dict[str, float] = {}

    def should_emit(self, field: str, value: Any, now: float) -> bool:
        """Check whether a field value passes both gates.

        Returns ``True`` if the value should be emitted downstream.
        """
        cfg = self._filters.get(field)
        if cfg is None or not cfg.enabled:
            return False

        # Throttle gate: enforce minimum interval
        if cfg.throttle_seconds > 0:
            last_time = self._last_emit_times.get(field)
            if last_time is not None and (now - last_time) < cfg.throttle_seconds:
                return False

        # Delta gate: value must have changed beyond granularity
        last_value = self._last_values.get(field)
        if last_value is None:
            # First value for this field — always emit
            return True

        if field in _LOCATION_FIELDS:
            delta = _location_delta(last_value, value)
        else:
            delta = _numeric_delta(last_value, value)

        # granularity=0 means any change triggers emission
        if cfg.granularity == 0:
            return bool(value != last_value)

        return delta >= cfg.granularity

    def record_emit(self, field: str, value: Any, now: float) -> None:
        """Record that a value was emitted (call after ``should_emit`` returns True)."""
        self._last_values[field] = value
        self._last_emit_times[field] = now

    def reset(self) -> None:
        """Clear all tracked state."""
        self._last_values.clear()
        self._last_emit_times.clear()
