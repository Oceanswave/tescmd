"""Bridge configuration for OpenClaw Gateway integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class NodeCapabilities(BaseModel):
    """Advertised capabilities for the OpenClaw node role.

    The node advertises only two commands to the gateway:

    - ``location.get`` (read) — standard node location capability
    - ``system.run`` (write) — single entry point; the gateway routes all
      invocations through this method and the internal
      :class:`~tescmd.openclaw.dispatcher.CommandDispatcher` fans out to
      the full set of 34 handlers.

    Maps to the gateway connect schema fields:
    - ``caps``: broad capability categories (``"location"``, ``"system"``)
    - ``commands``: specific method names the node can handle
    - ``permissions``: per-command permission booleans

    The ``reads`` and ``writes`` helpers provide a logical grouping that
    gets flattened into the gateway-native fields via :meth:`to_connect_params`.
    """

    reads: list[str] = [
        "location.get",
        "telemetry.get",
        "trigger.list",
        "trigger.poll",
    ]
    writes: list[str] = [
        "system.run",
        "trigger.create",
        "trigger.delete",
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
    max_seconds: float = Field(default=0.0, ge=0)
    """Maximum seconds of silence before forcing emission regardless of delta.

    A value of ``0`` disables the staleness gate (only delta + throttle apply).
    When set, ensures periodic updates even when values barely change —
    useful for numeric fields on an idle/parked vehicle.
    """


# Default filter configurations — low granularity thresholds so events
# flow frequently while still deduplicating truly identical values.
_DEFAULT_FILTERS: dict[str, FieldFilter] = {
    "Location": FieldFilter(granularity=5.0, throttle_seconds=1.0, max_seconds=60.0),
    "Soc": FieldFilter(granularity=0.5, throttle_seconds=10.0, max_seconds=120.0),
    "InsideTemp": FieldFilter(granularity=0.5, throttle_seconds=10.0, max_seconds=60.0),
    "OutsideTemp": FieldFilter(granularity=0.5, throttle_seconds=10.0, max_seconds=60.0),
    "VehicleSpeed": FieldFilter(granularity=1.0, throttle_seconds=2.0, max_seconds=30.0),
    "ChargeState": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "DetailedChargeState": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "Locked": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "SentryMode": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "BatteryLevel": FieldFilter(granularity=0.1, throttle_seconds=10.0, max_seconds=120.0),
    "EstBatteryRange": FieldFilter(granularity=1.0, throttle_seconds=10.0, max_seconds=120.0),
    "Odometer": FieldFilter(granularity=0.1, throttle_seconds=30.0, max_seconds=300.0),
    "Gear": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    "DefrostMode": FieldFilter(granularity=0.0, throttle_seconds=0.0),
}


class BridgeConfig(BaseModel):
    """Configuration for the OpenClaw telemetry bridge.

    Loaded from ``~/.config/tescmd/bridge.json``, CLI flags, or environment
    variables.
    """

    gateway_url: str = Field(
        default_factory=lambda: __import__("os").environ.get(
            "OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789"
        )
    )
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
