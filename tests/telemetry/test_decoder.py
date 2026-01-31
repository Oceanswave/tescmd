"""Tests for TelemetryDecoder — protobuf decoding of Fleet Telemetry Payload."""

from __future__ import annotations

import struct

from tescmd.protocol.protobuf.messages import (
    _encode_length_delimited,
    _encode_varint,
    _encode_varint_field,
)
from tescmd.telemetry.decoder import TelemetryDecoder, _zigzag_decode

# ---------------------------------------------------------------------------
# Protobuf encoding helpers (for crafting test payloads)
# ---------------------------------------------------------------------------


def _encode_tag(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_string_value(s: str) -> bytes:
    """Encode a Value message with string_value (field 1)."""
    return _encode_length_delimited(1, s.encode("utf-8"))


def _encode_int_value(n: int) -> bytes:
    """Encode a Value message with int_value (field 2, varint)."""
    return _encode_varint_field(2, n)


def _encode_float_value(f: float) -> bytes:
    """Encode a Value message with float_value (field 4, fixed32)."""
    tag = _encode_tag(4, 5)  # wire type 5 = 32-bit
    return tag + struct.pack("<f", f)


def _encode_double_value(d: float) -> bytes:
    """Encode a Value message with double_value (field 5, fixed64)."""
    tag = _encode_tag(5, 1)  # wire type 1 = 64-bit
    return tag + struct.pack("<d", d)


def _encode_bool_value(b: bool) -> bytes:
    """Encode a Value message with boolean_value (field 6, varint)."""
    return _encode_varint_field(6, int(b))


def _encode_location_value(lat: float, lng: float) -> bytes:
    """Encode a LocationValue sub-message (field 7)."""
    loc = b""
    loc += _encode_tag(1, 1) + struct.pack("<d", lat)
    loc += _encode_tag(2, 1) + struct.pack("<d", lng)
    return _encode_length_delimited(7, loc)


def _encode_datum(field_id: int, value_bytes: bytes) -> bytes:
    """Encode a Datum message: key (field 1) + value (field 2)."""
    datum = _encode_varint_field(1, field_id)
    datum += _encode_length_delimited(2, value_bytes)
    return datum


def _encode_timestamp(seconds: int, nanos: int = 0) -> bytes:
    """Encode a google.protobuf.Timestamp."""
    ts = _encode_varint_field(1, seconds)
    if nanos:
        ts += _encode_varint_field(2, nanos)
    return ts


def _encode_payload(
    data: list[bytes],
    timestamp_seconds: int = 1700000000,
    vin: str = "5YJ3E1EA1NF000001",
    is_resend: bool = False,
) -> bytes:
    """Encode a complete Payload message."""
    payload = b""
    for datum_bytes in data:
        payload += _encode_length_delimited(1, datum_bytes)
    payload += _encode_length_delimited(2, _encode_timestamp(timestamp_seconds))
    payload += _encode_length_delimited(3, vin.encode("utf-8"))
    if is_resend:
        payload += _encode_varint_field(4, 1)
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestZigzagDecode:
    def test_positive(self) -> None:
        assert _zigzag_decode(0) == 0
        assert _zigzag_decode(2) == 1
        assert _zigzag_decode(4) == 2
        assert _zigzag_decode(200) == 100

    def test_negative(self) -> None:
        assert _zigzag_decode(1) == -1
        assert _zigzag_decode(3) == -2
        assert _zigzag_decode(199) == -100


class TestDecodeStringValue:
    def test_string_datum(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(60, _encode_string_value("2024.8.9"))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert len(frame.data) == 1
        assert frame.data[0].field_name == "SoftwareVersion"
        assert frame.data[0].value == "2024.8.9"
        assert frame.data[0].value_type == "string"


class TestDecodeIntValue:
    def test_int_datum(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(8, _encode_int_value(72))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert len(frame.data) == 1
        assert frame.data[0].field_name == "BatteryLevel"
        assert frame.data[0].value == 72
        assert frame.data[0].value_type == "int"


class TestDecodeFloatValue:
    def test_float_datum(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(6, _encode_float_value(350.5))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert len(frame.data) == 1
        assert frame.data[0].field_name == "PackVoltage"
        assert abs(frame.data[0].value - 350.5) < 0.1
        assert frame.data[0].value_type == "float"


class TestDecodeDoubleValue:
    def test_double_datum(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(6, _encode_double_value(350.123456789))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert len(frame.data) == 1
        assert abs(frame.data[0].value - 350.123456789) < 1e-6
        assert frame.data[0].value_type == "float"


class TestDecodeBoolValue:
    def test_bool_true(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(51, _encode_bool_value(True))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert len(frame.data) == 1
        assert frame.data[0].field_name == "Locked"
        assert frame.data[0].value is True
        assert frame.data[0].value_type == "bool"

    def test_bool_false(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(51, _encode_bool_value(False))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert frame.data[0].value is False


class TestDecodeLocationValue:
    def test_location(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(9, _encode_location_value(37.7749, -122.4194))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert len(frame.data) == 1
        assert frame.data[0].field_name == "Location"
        assert frame.data[0].value_type == "location"
        loc = frame.data[0].value
        assert abs(loc["latitude"] - 37.7749) < 1e-4
        assert abs(loc["longitude"] - (-122.4194)) < 1e-4


class TestDecodePayload:
    def test_vin_and_timestamp(self) -> None:
        decoder = TelemetryDecoder()
        payload = _encode_payload([], timestamp_seconds=1700000000, vin="TEST_VIN")
        frame = decoder.decode(payload)
        assert frame.vin == "TEST_VIN"
        assert frame.created_at.year >= 2023

    def test_is_resend(self) -> None:
        decoder = TelemetryDecoder()
        payload = _encode_payload([], is_resend=True)
        frame = decoder.decode(payload)
        assert frame.is_resend is True

    def test_multiple_data_items(self) -> None:
        decoder = TelemetryDecoder()
        d1 = _encode_datum(3, _encode_int_value(85))
        d2 = _encode_datum(4, _encode_int_value(65))
        d3 = _encode_datum(33, _encode_float_value(22.5))
        payload = _encode_payload([d1, d2, d3])
        frame = decoder.decode(payload)
        assert len(frame.data) == 3
        names = {d.field_name for d in frame.data}
        assert names == {"Soc", "VehicleSpeed", "InsideTemp"}

    def test_unknown_field_id(self) -> None:
        decoder = TelemetryDecoder()
        datum_bytes = _encode_datum(9999, _encode_int_value(42))
        payload = _encode_payload([datum_bytes])
        frame = decoder.decode(payload)
        assert len(frame.data) == 1
        assert frame.data[0].field_name == "Unknown(9999)"

    def test_empty_payload(self) -> None:
        decoder = TelemetryDecoder()
        frame = decoder.decode(b"")
        assert frame.data == []
        assert frame.vin == ""
