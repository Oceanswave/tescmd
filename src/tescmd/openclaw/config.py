"""Bridge configuration for OpenClaw Gateway integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FieldFilter(BaseModel):
    """Per-field filter configuration for the dual-gate filter."""

    enabled: bool = True
    granularity: float = 0.0
    """Delta threshold — units depend on field type (meters, percent, degrees, etc.).

    A value of ``0`` means any change triggers emission.
    """
    throttle_seconds: float = 1.0
    """Minimum seconds between emissions for this field."""


# Default filter configurations per PRD
_DEFAULT_FILTERS: dict[str, FieldFilter] = {
    "Location": FieldFilter(granularity=50.0, throttle_seconds=1.0),
    "Soc": FieldFilter(granularity=5.0, throttle_seconds=10.0),
    "InsideTemp": FieldFilter(granularity=5.0, throttle_seconds=30.0),
    "OutsideTemp": FieldFilter(granularity=5.0, throttle_seconds=30.0),
    "VehicleSpeed": FieldFilter(granularity=5.0, throttle_seconds=2.0),
    "ChargeState": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "DetailedChargeState": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "Locked": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "SentryMode": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "BatteryLevel": FieldFilter(granularity=1.0, throttle_seconds=10.0),
    "EstBatteryRange": FieldFilter(granularity=5.0, throttle_seconds=30.0),
    "Odometer": FieldFilter(granularity=1.0, throttle_seconds=60.0),
    "Gear": FieldFilter(granularity=0.0, throttle_seconds=0.0),
}


class BridgeConfig(BaseModel):
    """Configuration for the OpenClaw telemetry bridge.

    Loaded from ``~/.config/tescmd/bridge.json``, CLI flags, or environment
    variables.
    """

    gateway_url: str = "ws://127.0.0.1:18789"
    gateway_token: str | None = Field(default=None)
    client_id: str = "tescmd-bridge"
    client_version: str = "0.1.0"
    telemetry: dict[str, FieldFilter] = Field(default_factory=lambda: dict(_DEFAULT_FILTERS))

    @classmethod
    def load(cls, path: Path | str | None = None) -> BridgeConfig:
        """Load configuration from a JSON file.

        Falls back to defaults if the file does not exist.
        """
        resolved = (
            Path("~/.config/tescmd/bridge.json").expanduser() if path is None else Path(path)
        )

        if not resolved.exists():
            return cls()

        raw = json.loads(resolved.read_text(encoding="utf-8"))
        return cls.model_validate(raw)

    def merge_overrides(
        self,
        *,
        gateway_url: str | None = None,
        gateway_token: str | None = None,
    ) -> BridgeConfig:
        """Return a new config with CLI flag overrides applied."""
        data: dict[str, Any] = self.model_dump()
        if gateway_url is not None:
            data["gateway_url"] = gateway_url
        if gateway_token is not None:
            data["gateway_token"] = gateway_token
        return BridgeConfig.model_validate(data)
