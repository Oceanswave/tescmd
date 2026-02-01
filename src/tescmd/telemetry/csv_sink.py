"""Wide-format CSV log sink for vehicle telemetry.

Writes one row per telemetry frame with one column per subscribed field.
The header extends dynamically as new fields are discovered.

Output format::

    timestamp,vin,BatteryLevel,ChargeLimitSoc,InsideTemp,...
    2026-02-01T12:34:55Z,5YJ3E...,80,90,22.5,...
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tescmd.telemetry.decoder import TelemetryFrame

logger = logging.getLogger(__name__)

# Fixed columns that always appear first.
_FIXED_COLUMNS = ("timestamp", "vin")

# Flush to disk every N frames for crash safety.
_FLUSH_INTERVAL = 10


def create_log_path(vin: str, config_dir: Path | None = None) -> Path:
    """Build a timestamped CSV log path under the config directory.

    Returns a path like ``~/.config/tescmd/logs/serve-{VIN}-{YYYYMMDD-HHMMSS}.csv``.
    Creates the ``logs/`` subdirectory if it does not exist.
    """
    if config_dir is None:
        config_dir = Path.home() / ".config" / "tescmd"
    log_dir = config_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return log_dir / f"serve-{vin}-{stamp}.csv"


class CSVLogSink:
    """Telemetry sink that writes wide-format CSV.

    Raw API values are written without unit conversion (Celsius, miles, bar)
    so the CSV is a faithful record of what the vehicle reported.

    Parameters:
        path: Destination CSV file path.
        vin: Only log frames matching this VIN (``None`` = log all).
    """

    def __init__(self, path: Path, vin: str | None = None) -> None:
        self._path = path
        self._vin = vin
        self._fh: IO[str] | None = None
        self._writer: csv.DictWriter[str] | None = None
        self._fieldnames: list[str] = list(_FIXED_COLUMNS)
        self._frame_count: int = 0
        self._since_flush: int = 0

    # -- Properties -----------------------------------------------------------

    @property
    def log_path(self) -> Path:
        """The CSV file path."""
        return self._path

    @property
    def frame_count(self) -> int:
        """Total frames written."""
        return self._frame_count

    # -- Sink callback --------------------------------------------------------

    async def on_frame(self, frame: TelemetryFrame) -> None:
        """Write a single telemetry frame as a CSV row.

        Called by :class:`~tescmd.telemetry.fanout.FrameFanout`.
        Frames for other VINs are silently skipped.
        """
        if self._vin is not None and frame.vin != self._vin:
            return

        # Build the row dict from frame data.
        row: dict[str, Any] = {
            "timestamp": frame.created_at.isoformat(),
            "vin": frame.vin,
        }
        for datum in frame.data:
            value = datum.value
            # Flatten location dicts to a string representation.
            if isinstance(value, dict):
                value = ";".join(f"{k}={v}" for k, v in value.items())
            row[datum.field_name] = value

        # Discover new fields and rewrite the header if needed.
        new_fields = [f for f in row if f not in self._fieldnames]
        if new_fields:
            self._fieldnames.extend(new_fields)
            if self._fh is not None:
                self._rewrite_header()

        # Lazily open the file on the first frame.
        if self._fh is None:
            self._open()

        assert self._writer is not None
        self._writer.writerow(row)
        self._frame_count += 1
        self._since_flush += 1

        if self._since_flush >= _FLUSH_INTERVAL:
            self._flush()

    # -- Lifecycle ------------------------------------------------------------

    def close(self) -> None:
        """Flush and close the CSV file."""
        if self._fh is not None:
            self._flush()
            self._fh.close()
            self._fh = None
            self._writer = None

    # -- Internals ------------------------------------------------------------

    def _open(self) -> None:
        """Open the CSV file and write the initial header."""
        self._fh = open(self._path, "w", newline="", encoding="utf-8")  # noqa: SIM115
        self._writer = csv.DictWriter(
            self._fh,
            fieldnames=self._fieldnames,
            extrasaction="ignore",
        )
        self._writer.writeheader()

    def _rewrite_header(self) -> None:
        """Rewrite the file with the expanded header, preserving existing rows.

        This is called when a new telemetry field is discovered mid-stream.
        The approach is: read existing content, rewrite with new fieldnames.
        """
        if self._fh is None:
            return

        self._fh.flush()
        self._fh.close()

        # Read existing rows.
        rows: list[dict[str, str]] = []
        with open(self._path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)

        # Rewrite with expanded header.
        self._fh = open(self._path, "w", newline="", encoding="utf-8")  # noqa: SIM115
        self._writer = csv.DictWriter(
            self._fh,
            fieldnames=self._fieldnames,
            extrasaction="ignore",
        )
        self._writer.writeheader()
        for r in rows:
            self._writer.writerow(r)

    def _flush(self) -> None:
        """Flush the file handle to disk."""
        if self._fh is not None:
            self._fh.flush()
            self._since_flush = 0
