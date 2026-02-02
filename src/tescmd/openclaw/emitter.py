"""Transform telemetry data into OpenClaw ``req:agent`` event payloads.

Maps Tesla Fleet Telemetry field names to OpenClaw event types as defined
in the PRD:

- ``Location``        → ``location``      {latitude, longitude, heading, speed}
- ``Soc``             → ``battery``        {battery_level, range_miles}
- ``InsideTemp``      → ``inside_temp``    {inside_temp_f}
- ``OutsideTemp``     → ``outside_temp``   {outside_temp_f}
- ``VehicleSpeed``    → ``speed``          {speed_mph}
- ``ChargeState``     → ``charge_started`` / ``charge_complete`` / ``charge_stopped``
- ``DetailedChargeState`` → same as ChargeState
- ``Locked`` / ``SentryMode`` → ``security_changed``
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


class EventEmitter:
    """Stateless transformer: telemetry datum → OpenClaw req:agent payload.

    Returns ``None`` for fields that don't map to an event type.
    """

    def __init__(self, client_id: str = "node-host") -> None:
        self._client_id = client_id

    def to_event(
        self,
        field_name: str,
        value: Any,
        vin: str,
        timestamp: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Convert a single telemetry datum to an OpenClaw event dict.

        Returns ``None`` if the field doesn't map to an event type.
        """
        ts = timestamp or datetime.now(UTC)
        ts_iso = ts.isoformat()

        payload = self._build_payload(field_name, value)
        if payload is None:
            return None

        event_type = payload.pop("_event_type")

        return {
            "method": "req:agent",
            "params": {
                "event_type": event_type,
                "source": self._client_id,
                "vin": vin,
                "timestamp": ts_iso,
                "data": payload,
            },
        }

    def _build_payload(self, field_name: str, value: Any) -> dict[str, Any] | None:
        """Build event-specific payload. Returns None for unmapped fields."""
        if field_name == "Location":
            return self._location_payload(value)
        if field_name == "Soc":
            return self._battery_payload(value)
        if field_name in ("InsideTemp", "OutsideTemp"):
            return self._temp_payload(field_name, value)
        if field_name == "VehicleSpeed":
            return self._speed_payload(value)
        if field_name in ("ChargeState", "DetailedChargeState"):
            return self._charge_state_payload(value)
        if field_name in ("Locked", "SentryMode"):
            return self._security_payload(field_name, value)
        if field_name == "BatteryLevel":
            return self._battery_level_payload(value)
        if field_name == "EstBatteryRange":
            return self._range_payload(value)
        if field_name == "Gear":
            return self._gear_payload(value)
        return None

    def _location_payload(self, value: Any) -> dict[str, Any] | None:
        try:
            return {
                "_event_type": "location",
                "latitude": float(value["latitude"]),
                "longitude": float(value["longitude"]),
                "heading": float(value.get("heading", 0)),
                "speed": float(value.get("speed", 0)),
            }
        except (TypeError, KeyError, ValueError):
            return None

    def _battery_payload(self, value: Any) -> dict[str, Any] | None:
        try:
            return {
                "_event_type": "battery",
                "battery_level": float(value),
            }
        except (TypeError, ValueError):
            return None

    def _temp_payload(self, field_name: str, value: Any) -> dict[str, Any] | None:
        try:
            temp_c = float(value)
            temp_f = _celsius_to_fahrenheit(temp_c)
            event_type = "inside_temp" if field_name == "InsideTemp" else "outside_temp"
            key = f"{event_type}_f"
            return {
                "_event_type": event_type,
                key: round(temp_f, 1),
            }
        except (TypeError, ValueError):
            return None

    def _speed_payload(self, value: Any) -> dict[str, Any] | None:
        try:
            return {
                "_event_type": "speed",
                "speed_mph": float(value),
            }
        except (TypeError, ValueError):
            return None

    def _charge_state_payload(self, value: Any) -> dict[str, Any] | None:
        state = str(value).lower()
        if "charging" in state or state == "starting":
            event_type = "charge_started"
        elif "complete" in state:
            event_type = "charge_complete"
        elif "stopped" in state or "disconnected" in state:
            event_type = "charge_stopped"
        else:
            event_type = "charge_state_changed"
        return {
            "_event_type": event_type,
            "state": str(value),
        }

    def _security_payload(self, field_name: str, value: Any) -> dict[str, Any] | None:
        return {
            "_event_type": "security_changed",
            "field": field_name.lower(),
            "value": value,
        }

    def _battery_level_payload(self, value: Any) -> dict[str, Any] | None:
        try:
            return {
                "_event_type": "battery",
                "battery_level": float(value),
            }
        except (TypeError, ValueError):
            return None

    def _range_payload(self, value: Any) -> dict[str, Any] | None:
        try:
            return {
                "_event_type": "battery",
                "range_miles": float(value),
            }
        except (TypeError, ValueError):
            return None

    def _gear_payload(self, value: Any) -> dict[str, Any] | None:
        return {
            "_event_type": "gear_changed",
            "gear": str(value),
        }
