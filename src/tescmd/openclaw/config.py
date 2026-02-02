"""Bridge configuration for OpenClaw Gateway integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class NodeCapabilities(BaseModel):
    """Advertised capabilities for the OpenClaw node role.

    Maps to the gateway connect schema fields:
    - ``caps``: broad capability categories (e.g. ``"location"``, ``"climate"``)
    - ``commands``: specific method names the node can handle
    - ``permissions``: per-command permission booleans

    The ``reads`` and ``writes`` helpers provide a logical grouping that
    gets flattened into the gateway-native fields via :meth:`to_connect_params`.
    """

    reads: list[str] = [
        "location.get",
        "battery.get",
        "temperature.get",
        "speed.get",
        "charge_state.get",
        "security.get",
        # Trigger reads
        "trigger.list",
        "trigger.poll",
    ]
    writes: list[str] = [
        "door.lock",
        "door.unlock",
        "climate.on",
        "climate.off",
        "climate.set_temp",
        "charge.start",
        "charge.stop",
        "charge.set_limit",
        "trunk.open",
        "frunk.open",
        "flash_lights",
        "honk_horn",
        "sentry.on",
        "sentry.off",
        # Trigger writes
        "trigger.create",
        "trigger.delete",
        # Convenience trigger aliases
        "cabin_temp.trigger",
        "outside_temp.trigger",
        "battery.trigger",
        "location.trigger",
        # Meta-dispatch
        "system.run",
    ]

    @property
    def all_commands(self) -> list[str]:
        """All command method names (reads + writes), deduplicated."""
        return list(dict.fromkeys(self.reads + self.writes))

    @property
    def caps(self) -> list[str]:
        """Unique capability categories derived from command prefixes."""
        seen: dict[str, None] = {}
        for cmd in self.all_commands:
            category = cmd.split(".")[0] if "." in cmd else cmd
            seen.setdefault(category, None)
        return list(seen)

    @property
    def permissions(self) -> dict[str, bool]:
        """Per-command permissions (all ``True`` for advertised commands)."""
        return {cmd: True for cmd in self.all_commands}

    def to_connect_params(self) -> dict[str, Any]:
        """Return the gateway-native connect param fields."""
        return {
            "caps": self.caps,
            "commands": self.all_commands,
            "permissions": self.permissions,
        }


class FieldFilter(BaseModel):
    """Per-field filter configuration for the dual-gate filter."""

    enabled: bool = True
    granularity: float = Field(default=0.0, ge=0)
    """Delta threshold — units depend on field type (meters, percent, degrees, etc.).

    A value of ``0`` means any change triggers emission.
    """
    throttle_seconds: float = Field(default=1.0, ge=0)
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
    client_id: str = "node-host"
    client_version: str | None = None
    telemetry: dict[str, FieldFilter] = Field(default_factory=lambda: dict(_DEFAULT_FILTERS))
    capabilities: NodeCapabilities = Field(default_factory=NodeCapabilities)

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
