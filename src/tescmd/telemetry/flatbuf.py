"""Minimal Flatbuffers reader for Tesla Fleet Telemetry envelopes.

Tesla vehicles send telemetry data wrapped in a Flatbuffers envelope:

    WebSocket binary frame
      └─ FlatbuffersEnvelope
           ├── txid          (bytes)
           ├── topic         (bytes)  — "V", "alerts", "errors", "connectivity"
           ├── messageType   (uint8)
           ├── messageId     (bytes)
           └── FlatbuffersStream (union)
                  ├── createdAt  (uint32)  — epoch seconds
                  ├── payload    (bytes)   — protobuf content
                  ├── deviceId   (bytes)   — VIN
                  └── ...

This module provides a zero-dependency reader for these two tables.
The protobuf payload inside ``FlatbuffersStream.payload`` is decoded
separately by :mod:`tescmd.telemetry.decoder`.

Schema source:
  https://github.com/teslamotors/fleet-telemetry/tree/main/messages/tesla
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


@dataclass(slots=True)
class StreamMessage:
    """Unwrapped Fleet Telemetry envelope."""

    topic: bytes
    device_id: bytes  # VIN
    created_at: int  # epoch seconds
    payload: bytes  # protobuf content
    txid: bytes = b""
    message_id: bytes = b""


def parse_envelope(buf: bytes) -> StreamMessage:
    """Parse a FlatbuffersEnvelope from raw WebSocket bytes.

    Raises:
        ValueError: If the buffer is too small or structurally invalid.
    """
    if len(buf) < 8:
        raise ValueError(f"Buffer too small for Flatbuffers envelope ({len(buf)} bytes)")

    # Root table offset (uint32 LE at byte 0)
    root_pos = _read_u32(buf, 0)
    if root_pos >= len(buf):
        raise ValueError(f"Root offset {root_pos} exceeds buffer size {len(buf)}")

    # Envelope vtable
    vtable_pos = _vtable_pos(buf, root_pos)

    # Envelope fields (vtable offsets: txid=4, topic=6, messageType=8, message=10, messageId=12)
    txid = _read_vector(buf, root_pos, vtable_pos, vtable_offset=4)
    topic = _read_vector(buf, root_pos, vtable_pos, vtable_offset=6)
    message_id = _read_vector(buf, root_pos, vtable_pos, vtable_offset=12)

    # Navigate to FlatbuffersStream (union at vtable_offset=10)
    stream_pos = _read_indirect(buf, root_pos, vtable_pos, vtable_offset=10)
    if stream_pos is None:
        raise ValueError("FlatbuffersEnvelope has no message field")

    # Stream vtable
    stream_vtable = _vtable_pos(buf, stream_pos)

    # Stream fields (vtable offsets: createdAt=4, senderId=6, payload=8,
    #                deviceType=10, deviceId=12, deliveredAtEpochMs=14)
    created_at = _read_u32_field(buf, stream_pos, stream_vtable, vtable_offset=4)
    payload = _read_vector(buf, stream_pos, stream_vtable, vtable_offset=8)
    device_id = _read_vector(buf, stream_pos, stream_vtable, vtable_offset=12)

    return StreamMessage(
        topic=topic,
        device_id=device_id,
        created_at=created_at,
        payload=payload,
        txid=txid,
        message_id=message_id,
    )


# ---------------------------------------------------------------------------
# Low-level Flatbuffers primitives
# ---------------------------------------------------------------------------


def _read_u16(buf: bytes, pos: int) -> int:
    result: int = struct.unpack_from("<H", buf, pos)[0]
    return result


def _read_u32(buf: bytes, pos: int) -> int:
    result: int = struct.unpack_from("<I", buf, pos)[0]
    return result


def _read_i32(buf: bytes, pos: int) -> int:
    result: int = struct.unpack_from("<i", buf, pos)[0]
    return result


def _vtable_pos(buf: bytes, table_pos: int) -> int:
    """Compute vtable position from a table position.

    The first 4 bytes of a Flatbuffers table are a signed offset (soffset32)
    pointing back to its vtable.
    """
    soffset = _read_i32(buf, table_pos)
    return table_pos - soffset


def _field_offset(buf: bytes, vtable_pos: int, vtable_offset: int) -> int:
    """Read a field's offset from the vtable.

    Returns 0 if the field is absent (vtable_offset beyond vtable size
    or stored offset is 0).
    """
    vtable_size = _read_u16(buf, vtable_pos)
    if vtable_offset >= vtable_size:
        return 0
    return _read_u16(buf, vtable_pos + vtable_offset)


def _read_vector(buf: bytes, table_pos: int, vtable_pos: int, *, vtable_offset: int) -> bytes:
    """Read a byte-vector field from a Flatbuffers table."""
    voff = _field_offset(buf, vtable_pos, vtable_offset)
    if voff == 0:
        return b""
    # Follow indirect offset to vector
    field_pos = table_pos + voff
    vec_pos = field_pos + _read_u32(buf, field_pos)
    length = _read_u32(buf, vec_pos)
    return bytes(buf[vec_pos + 4 : vec_pos + 4 + length])


def _read_u32_field(buf: bytes, table_pos: int, vtable_pos: int, *, vtable_offset: int) -> int:
    """Read a uint32 scalar field from a Flatbuffers table."""
    voff = _field_offset(buf, vtable_pos, vtable_offset)
    if voff == 0:
        return 0
    return _read_u32(buf, table_pos + voff)


def _read_indirect(
    buf: bytes, table_pos: int, vtable_pos: int, *, vtable_offset: int
) -> int | None:
    """Follow an offset field to a child table (used for unions).

    Returns the child table position, or ``None`` if absent.
    """
    voff = _field_offset(buf, vtable_pos, vtable_offset)
    if voff == 0:
        return None
    field_pos = table_pos + voff
    return field_pos + _read_u32(buf, field_pos)
