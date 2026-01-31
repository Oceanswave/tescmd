"""Decode protobuf-encoded Fleet Telemetry Payload messages.

Reuses the low-level varint / field decoders from
:mod:`tescmd.protocol.protobuf.messages` to parse the telemetry wire
format without vendoring ``.proto`` files.

Telemetry Payload wire format (from fleet_telemetry.proto):
  message Payload {
    repeated Datum data = 1;
    google.protobuf.Timestamp created_at = 2;
    string vin = 3;
    bool is_resend = 4;
  }

  message Datum {
    Field key = 1;        // varint enum
    Value value = 2;      // sub-message
  }

  message Value {
    oneof value {
      string string_value = 1;
      int32 int_value = 2;
      int64 long_value = 3;
      float float_value = 4;
      double double_value = 5;
      bool boolean_value = 6;
      LocationValue location_value = 7;
    }
  }

  message LocationValue {
    double latitude = 1;
    double longitude = 2;
  }
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from tescmd.protocol.protobuf.messages import _decode_field
from tescmd.telemetry.fields import FIELD_NAMES

logger = logging.getLogger(__name__)


@dataclass
class TelemetryDatum:
    """A single decoded telemetry field."""

    field_name: str
    field_id: int
    value: Any
    value_type: str  # "string", "int", "float", "bool", "location"


@dataclass
class TelemetryFrame:
    """A decoded telemetry payload from one vehicle push."""

    vin: str
    created_at: datetime
    data: list[TelemetryDatum] = field(default_factory=list)
    is_resend: bool = False


class TelemetryDecoder:
    """Decodes binary protobuf Payload messages into :class:`TelemetryFrame`."""

    def decode(self, raw: bytes) -> TelemetryFrame:
        """Decode a Payload protobuf message.

        Args:
            raw: The raw protobuf bytes.

        Returns:
            A :class:`TelemetryFrame` with decoded telemetry data.

        Raises:
            ValueError: If the message is fundamentally malformed.
        """
        data_items: list[TelemetryDatum] = []
        created_at = datetime.now(tz=UTC)
        vin = ""
        is_resend = False

        pos = 0
        while pos < len(raw):
            field_number, wire_type, value, pos = _decode_field(raw, pos)

            if field_number == 1 and wire_type == 2:
                # repeated Datum — length-delimited sub-message
                datum = self._decode_datum(value)
                if datum is not None:
                    data_items.append(datum)
            elif field_number == 2 and wire_type == 2:
                # google.protobuf.Timestamp sub-message
                created_at = self._decode_timestamp(value)
            elif field_number == 3 and wire_type == 2:
                # string vin
                vin = value.decode("utf-8", errors="replace")
            elif field_number == 4 and wire_type == 0:
                # bool is_resend
                is_resend = bool(value)

        return TelemetryFrame(
            vin=vin,
            created_at=created_at,
            data=data_items,
            is_resend=is_resend,
        )

    def _decode_datum(self, raw: bytes) -> TelemetryDatum | None:
        """Decode a single Datum sub-message."""
        field_id = 0
        value: Any = None
        value_type = "unknown"

        pos = 0
        while pos < len(raw):
            fn, wt, val, pos = _decode_field(raw, pos)
            if fn == 1 and wt == 0:
                field_id = val
            elif fn == 2 and wt == 2:
                value, value_type = self._decode_value(val)

        if field_id == 0:
            return None

        field_name = FIELD_NAMES.get(field_id, f"Unknown({field_id})")
        return TelemetryDatum(
            field_name=field_name,
            field_id=field_id,
            value=value,
            value_type=value_type,
        )

    def _decode_value(self, raw: bytes) -> tuple[Any, str]:
        """Decode a Value oneof sub-message.

        Returns ``(decoded_value, type_name)``.
        """
        pos = 0
        while pos < len(raw):
            fn, wt, val, pos = _decode_field(raw, pos)

            if fn == 1 and wt == 2:
                return val.decode("utf-8", errors="replace"), "string"
            elif fn == 2 and wt == 0:
                # int32 — regular varint (not zigzag)
                return val, "int"
            elif fn == 3 and wt == 0:
                # int64 — regular varint (not zigzag)
                return val, "int"
            elif fn == 4 and wt == 5:
                # float — wire type 5 = 32-bit
                return struct.unpack("<f", struct.pack("<I", val))[0], "float"
            elif fn == 5 and wt == 1:
                # double — wire type 1 = 64-bit
                return struct.unpack("<d", struct.pack("<Q", val))[0], "float"
            elif fn == 6 and wt == 0:
                return bool(val), "bool"
            elif fn == 7 and wt == 2:
                return self._decode_location(val), "location"

        return None, "unknown"

    @staticmethod
    def _decode_location(raw: bytes) -> dict[str, float]:
        """Decode a LocationValue sub-message."""
        lat = 0.0
        lng = 0.0
        pos = 0
        while pos < len(raw):
            fn, wt, val, pos = _decode_field(raw, pos)
            if fn == 1 and wt == 1:
                lat = struct.unpack("<d", struct.pack("<Q", val))[0]
            elif fn == 2 and wt == 1:
                lng = struct.unpack("<d", struct.pack("<Q", val))[0]
        return {"latitude": lat, "longitude": lng}

    @staticmethod
    def _decode_timestamp(raw: bytes) -> datetime:
        """Decode a google.protobuf.Timestamp sub-message.

        Timestamp: field 1 = seconds (int64), field 2 = nanos (int32).
        """
        seconds = 0
        nanos = 0
        pos = 0
        while pos < len(raw):
            fn, wt, val, pos = _decode_field(raw, pos)
            if fn == 1 and wt == 0:
                seconds = val
            elif fn == 2 and wt == 0:
                nanos = val

        ts = seconds + nanos / 1_000_000_000
        return datetime.fromtimestamp(ts, tz=UTC)


def _zigzag_decode(n: int) -> int:
    """Decode a ZigZag-encoded signed integer."""
    return (n >> 1) ^ -(n & 1)
