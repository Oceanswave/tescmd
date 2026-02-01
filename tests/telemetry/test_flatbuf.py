"""Tests for the Flatbuffers envelope parser."""

from __future__ import annotations

import struct

import pytest

from tescmd.telemetry.flatbuf import parse_envelope


def build_flatbuf_envelope(
    payload: bytes,
    *,
    topic: bytes = b"V",
    device_id: bytes = b"TEST_VIN",
    created_at: int = 1700000000,
    txid: bytes = b"tx-1",
    message_id: bytes = b"msg-1",
) -> bytes:
    """Build a minimal Flatbuffers envelope for testing.

    Constructs a valid FlatbuffersEnvelope + FlatbuffersStream that
    ``parse_envelope()`` can decode.  Tables are placed first, then
    vectors, so all indirect offsets point forward (positive).
    """
    # We'll build the buffer in sections, then fix up offsets.
    # Layout:
    #   [4] root_offset
    #   [env_vtable]
    #   [env_table]
    #   [stream_vtable]
    #   [stream_table]
    #   [vectors: txid, topic, message_id, payload, device_id]

    buf = bytearray()

    # Reserve root offset (4 bytes)
    buf.extend(b"\x00\x00\x00\x00")

    # --- Envelope vtable (5 fields: txid, topic, msgType, message, msgId) ---
    env_vtable_pos = len(buf)
    buf.extend(struct.pack("<H", 14))  # vtable size = 4 + 5*2 = 14
    buf.extend(struct.pack("<H", 24))  # table data size
    buf.extend(struct.pack("<H", 4))  # field 0 (txid) at offset 4
    buf.extend(struct.pack("<H", 8))  # field 1 (topic) at offset 8
    buf.extend(struct.pack("<H", 12))  # field 2 (messageType) at offset 12
    buf.extend(struct.pack("<H", 16))  # field 3 (message) at offset 16
    buf.extend(struct.pack("<H", 20))  # field 4 (messageId) at offset 20

    # --- Envelope table ---
    env_table_pos = len(buf)
    # soffset32 to vtable (table_pos - vtable_pos)
    buf.extend(struct.pack("<i", env_table_pos - env_vtable_pos))
    # field 0: txid offset (placeholder) — at env_table_pos + 4
    txid_off_pos = len(buf)
    buf.extend(b"\x00\x00\x00\x00")
    # field 1: topic offset (placeholder) — at env_table_pos + 8
    topic_off_pos = len(buf)
    buf.extend(b"\x00\x00\x00\x00")
    # field 2: messageType (u8) — at env_table_pos + 12, padded to 4
    buf.append(4)  # FlatbuffersStream type
    buf.extend(b"\x00\x00\x00")
    # field 3: message (offset to stream table) — at env_table_pos + 16
    message_off_pos = len(buf)
    buf.extend(b"\x00\x00\x00\x00")
    # field 4: messageId offset (placeholder) — at env_table_pos + 20
    msgid_off_pos = len(buf)
    buf.extend(b"\x00\x00\x00\x00")

    assert len(buf) - env_table_pos == 24  # table data size

    # --- Stream vtable (6 fields) ---
    stream_vtable_pos = len(buf)
    buf.extend(struct.pack("<H", 16))  # vtable size = 4 + 6*2 = 16
    buf.extend(struct.pack("<H", 20))  # table data size
    buf.extend(struct.pack("<H", 4))  # field 0: createdAt at offset 4
    buf.extend(struct.pack("<H", 0))  # field 1: senderId (absent)
    buf.extend(struct.pack("<H", 8))  # field 2: payload at offset 8
    buf.extend(struct.pack("<H", 0))  # field 3: deviceType (absent)
    buf.extend(struct.pack("<H", 12))  # field 4: deviceId at offset 12
    buf.extend(struct.pack("<H", 0))  # field 5: deliveredAtEpochMs (absent)

    # --- Stream table ---
    stream_table_pos = len(buf)
    # soffset32 to vtable
    buf.extend(struct.pack("<i", stream_table_pos - stream_vtable_pos))
    # field 0: createdAt (u32) at offset 4
    buf.extend(struct.pack("<I", created_at))
    # field 2: payload offset (placeholder) at offset 8
    payload_off_pos = len(buf)
    buf.extend(b"\x00\x00\x00\x00")
    # field 4: deviceId offset (placeholder) at offset 12
    devid_off_pos = len(buf)
    buf.extend(b"\x00\x00\x00\x00")
    # pad to table data size (20 bytes)
    while len(buf) - stream_table_pos < 20:
        buf.append(0)

    # --- Vectors (placed AFTER tables so offsets are positive) ---
    def _write_vector(data: bytes) -> int:
        # Align to 4
        while len(buf) % 4 != 0:
            buf.append(0)
        pos = len(buf)
        buf.extend(struct.pack("<I", len(data)))
        buf.extend(data)
        return pos

    txid_vec = _write_vector(txid)
    topic_vec = _write_vector(topic)
    msgid_vec = _write_vector(message_id)
    payload_vec = _write_vector(payload)
    devid_vec = _write_vector(device_id)

    # --- Patch offsets (relative to the field's own position) ---
    struct.pack_into("<I", buf, txid_off_pos, txid_vec - txid_off_pos)
    struct.pack_into("<I", buf, topic_off_pos, topic_vec - topic_off_pos)
    struct.pack_into("<I", buf, msgid_off_pos, msgid_vec - msgid_off_pos)
    struct.pack_into("<I", buf, payload_off_pos, payload_vec - payload_off_pos)
    struct.pack_into("<I", buf, devid_off_pos, devid_vec - devid_off_pos)

    # Patch message offset (envelope → stream table)
    struct.pack_into("<I", buf, message_off_pos, stream_table_pos - message_off_pos)

    # Patch root offset (byte 0 → envelope table)
    struct.pack_into("<I", buf, 0, env_table_pos)

    return bytes(buf)


class TestParseEnvelope:
    def test_basic_envelope(self) -> None:
        protobuf_payload = b"\x01\x02\x03"
        raw = build_flatbuf_envelope(
            protobuf_payload,
            topic=b"V",
            device_id=b"TEST_VIN_123",
            created_at=1700000000,
        )
        msg = parse_envelope(raw)
        assert msg.topic == b"V"
        assert msg.device_id == b"TEST_VIN_123"
        assert msg.created_at == 1700000000
        assert msg.payload == protobuf_payload
        assert msg.txid == b"tx-1"
        assert msg.message_id == b"msg-1"

    def test_too_small_buffer(self) -> None:
        with pytest.raises(ValueError, match="too small"):
            parse_envelope(b"\x00\x00")

    def test_roundtrip_with_decoder(self) -> None:
        """Full pipeline: Flatbuffers envelope -> protobuf Payload -> TelemetryFrame."""
        from tescmd.telemetry.protos import vehicle_data_pb2

        pb_payload = vehicle_data_pb2.Payload(
            data=[
                vehicle_data_pb2.Datum(
                    key=vehicle_data_pb2.BatteryLevel,
                    value=vehicle_data_pb2.Value(int_value=72),
                ),
            ],
            vin="5YJ3E1EA1NF000001",
        )
        raw = build_flatbuf_envelope(
            pb_payload.SerializeToString(),
            device_id=b"5YJ3E1EA1NF000001",
        )

        from tescmd.telemetry.decoder import TelemetryDecoder

        decoder = TelemetryDecoder()
        frame = decoder.decode(raw)

        assert frame.vin == "5YJ3E1EA1NF000001"
        assert len(frame.data) == 1
        assert frame.data[0].field_name == "BatteryLevel"
        assert frame.data[0].value == 72
