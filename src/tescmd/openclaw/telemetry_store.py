"""In-memory store for the latest telemetry values per field.

Used by :class:`CommandDispatcher` to serve read requests from cached
telemetry data before falling back to the Fleet API. Updated on every
decoded frame by :class:`TelemetryBridge`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(slots=True)
class FieldSnapshot:
    """A single telemetry field's most recent value."""

    value: Any
    timestamp: datetime


class TelemetryStore:
    """Thread-safe (single-event-loop) store of latest telemetry values.

    Keyed by the Tesla Fleet Telemetry field name (e.g. ``"Soc"``,
    ``"Location"``, ``"Locked"``).
    """

    def __init__(self) -> None:
        self._data: dict[str, FieldSnapshot] = {}

    def update(self, field_name: str, value: Any, timestamp: datetime) -> None:
        """Record or overwrite the latest value for *field_name*."""
        self._data[field_name] = FieldSnapshot(value=value, timestamp=timestamp)

    def get(self, field_name: str) -> FieldSnapshot | None:
        """Return the latest snapshot for *field_name*, or ``None``."""
        return self._data.get(field_name)

    def get_all(self) -> dict[str, FieldSnapshot]:
        """Return a shallow copy of all current snapshots."""
        return dict(self._data)

    def age_seconds(self, field_name: str) -> float | None:
        """Return seconds since *field_name* was last updated, or ``None``."""
        snap = self._data.get(field_name)
        if snap is None:
            return None
        return time.time() - snap.timestamp.timestamp()
