"""Decode Fleet Telemetry messages from Tesla vehicles.

Tesla vehicles send telemetry data as **Flatbuffers envelopes** wrapping
protobuf payloads.  The :class:`TelemetryDecoder` handles both layers:

1. Unwrap the Flatbuffers ``FlatbuffersEnvelope`` → ``FlatbuffersStream``
   to extract the topic, VIN, timestamp, and raw protobuf bytes.
2. Decode the protobuf ``Payload`` message using generated bindings from
   Tesla's ``vehicle_data.proto``.

Proto source: https://github.com/teslamotors/fleet-telemetry/tree/main/protos
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Value oneof variants that are enum types (wire varint) — map to enum name.
_ENUM_VARIANTS: frozenset[str] = frozenset(
    {
        "charging_value",
        "shift_state_value",
        "lane_assist_level_value",
        "scheduled_charging_mode_value",
        "sentry_mode_state_value",
        "speed_assist_level_value",
        "bms_state_value",
        "buckle_status_value",
        "car_type_value",
        "charge_port_value",
        "charge_port_latch_value",
        "drive_inverter_state_value",
        "hvil_status_value",
        "window_state_value",
        "seat_fold_position_value",
        "tractor_air_status_value",
        "follow_distance_value",
        "forward_collision_sensitivity_value",
        "guest_mode_mobile_access_value",
        "trailer_air_status_value",
        "detailed_charge_state_value",
        "hvac_auto_mode_value",
        "cabin_overheat_protection_mode_value",
        "cabin_overheat_protection_temperature_limit_value",
        "defrost_mode_value",
        "climate_keeper_mode_value",
        "hvac_power_value",
        "fast_charger_value",
        "cable_type_value",
        "tonneau_tent_mode_value",
        "tonneau_position_value",
        "powershare_type_value",
        "powershare_state_value",
        "powershare_stop_reason_value",
        "display_state_value",
        "distance_unit_value",
        "temperature_unit_value",
        "pressure_unit_value",
        "charge_unit_preference_value",
        "turn_signal_state_value",
        "media_status_value",
        "sunroof_installed_state_value",
    }
)


@dataclass
class TelemetryDatum:
    """A single decoded telemetry field."""

    field_name: str
    field_id: int
    value: Any
    value_type: str  # "string", "int", "float", "bool", "location", "enum"


@dataclass
class TelemetryFrame:
    """A decoded telemetry payload from one vehicle push."""

    vin: str
    created_at: datetime
    data: list[TelemetryDatum] = field(default_factory=list)
    is_resend: bool = False
    topic: str = "V"


class TelemetryDecoder:
    """Decodes binary Fleet Telemetry messages into :class:`TelemetryFrame`.

    Handles the full Flatbuffers → protobuf pipeline.
    """

    def decode(self, raw: bytes) -> TelemetryFrame:
        """Decode a raw WebSocket binary message.

        The message is expected to be a Flatbuffers ``FlatbuffersEnvelope``
        containing a ``FlatbuffersStream`` with a protobuf payload.

        Args:
            raw: The raw binary WebSocket message.

        Returns:
            A :class:`TelemetryFrame` with decoded telemetry data.

        Raises:
            ValueError: If the message is fundamentally malformed.
        """
        from tescmd.telemetry.flatbuf import parse_envelope

        envelope = parse_envelope(raw)
        topic = envelope.topic.decode("utf-8", errors="replace")
        vin = envelope.device_id.decode("utf-8", errors="replace")
        created_at = datetime.fromtimestamp(envelope.created_at, tz=UTC)

        if topic != "V":
            # Non-telemetry topics (alerts, errors, connectivity) — return
            # a frame with no data items for now.
            logger.debug("Received non-telemetry topic: %s", topic)
            return TelemetryFrame(
                vin=vin,
                created_at=created_at,
                topic=topic,
            )

        return self._decode_payload(envelope.payload, vin, created_at, topic)

    def decode_protobuf(self, raw: bytes) -> TelemetryFrame:
        """Decode a raw protobuf ``Payload`` message directly.

        Bypasses the Flatbuffers envelope — use this when the envelope has
        already been unwrapped, or for testing with hand-crafted protobuf.

        Args:
            raw: Raw protobuf bytes of a ``Payload`` message.

        Returns:
            A :class:`TelemetryFrame` with decoded telemetry data.
        """
        return self._decode_payload(raw, vin="", created_at=datetime.now(tz=UTC), topic="V")

    def _decode_payload(
        self,
        payload_bytes: bytes,
        vin: str,
        created_at: datetime,
        topic: str,
    ) -> TelemetryFrame:
        """Decode the protobuf Payload message using generated bindings."""
        from tescmd.telemetry.protos import vehicle_data_pb2

        payload = vehicle_data_pb2.Payload()
        payload.ParseFromString(payload_bytes)

        # Use VIN and timestamp from protobuf if present (more accurate
        # than the Flatbuffers envelope which has second granularity).
        if payload.vin:
            vin = payload.vin
        if payload.HasField("created_at"):
            ts = payload.created_at
            created_at = datetime.fromtimestamp(ts.seconds + ts.nanos / 1_000_000_000, tz=UTC)

        data_items: list[TelemetryDatum] = []
        for datum in payload.data:
            item = self._decode_datum(datum)
            if item is not None:
                data_items.append(item)

        return TelemetryFrame(
            vin=vin,
            created_at=created_at,
            data=data_items,
            is_resend=payload.is_resend,
            topic=topic,
        )

    @staticmethod
    def _decode_datum(
        datum: Any,
    ) -> TelemetryDatum | None:
        """Extract a single Datum into a TelemetryDatum."""
        from tescmd.telemetry.protos import vehicle_data_pb2

        field_id: int = datum.key
        if field_id == 0:
            return None

        # Get field name from proto enum, fall back to our registry
        try:
            field_name = vehicle_data_pb2.Field.Name(field_id)
        except ValueError:
            from tescmd.telemetry.fields import FIELD_NAMES

            field_name = FIELD_NAMES.get(field_id, f"Unknown({field_id})")

        value_msg = datum.value
        which = value_msg.WhichOneof("value")
        if which is None:
            return None

        val: Any
        value_type: str

        # --- Primitive types ---
        if which == "string_value":
            val, value_type = value_msg.string_value, "string"
        elif which == "int_value":
            val, value_type = value_msg.int_value, "int"
        elif which == "long_value":
            val, value_type = value_msg.long_value, "int"
        elif which == "float_value":
            val, value_type = value_msg.float_value, "float"
        elif which == "double_value":
            val, value_type = value_msg.double_value, "float"
        elif which == "boolean_value":
            val, value_type = value_msg.boolean_value, "bool"
        elif which == "invalid":
            val, value_type = None, "invalid"

        # --- Structured types ---
        elif which == "location_value":
            loc = value_msg.location_value
            val = {"latitude": loc.latitude, "longitude": loc.longitude}
            value_type = "location"
        elif which == "door_value":
            doors = value_msg.door_value
            val = {
                "DriverFront": doors.DriverFront,
                "DriverRear": doors.DriverRear,
                "PassengerFront": doors.PassengerFront,
                "PassengerRear": doors.PassengerRear,
                "TrunkFront": doors.TrunkFront,
                "TrunkRear": doors.TrunkRear,
            }
            value_type = "doors"
        elif which == "tire_location_value":
            tire = value_msg.tire_location_value
            val = {
                "front_left": tire.front_left,
                "front_right": tire.front_right,
                "rear_left": tire.rear_left,
                "rear_right": tire.rear_right,
            }
            value_type = "tires"
        elif which == "time_value":
            t = value_msg.time_value
            val = f"{t.hour:02d}:{t.minute:02d}:{t.second:02d}"
            value_type = "time"

        # --- Enum types → resolve to human-readable name ---
        elif which in _ENUM_VARIANTS:
            raw_val = getattr(value_msg, which)
            # Enum fields are ints; get the name from the descriptor
            enum_descriptor = value_msg.DESCRIPTOR.fields_by_name[which].enum_type
            if enum_descriptor is not None:
                try:
                    val = enum_descriptor.values_by_number[raw_val].name
                except (KeyError, IndexError):
                    val = raw_val
            else:
                val = raw_val
            value_type = "enum"

        else:
            # Unknown variant — store the raw value
            val = getattr(value_msg, which, None)
            value_type = which

        return TelemetryDatum(
            field_name=field_name,
            field_id=field_id,
            value=val,
            value_type=value_type,
        )


def _zigzag_decode(n: int) -> int:
    """Decode a ZigZag-encoded signed integer."""
    return (n >> 1) ^ -(n & 1)
