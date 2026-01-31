"""TLV (tag-length-value) metadata serialization for command authentication.

The metadata block is a sequence of TLV entries that are fed into the HMAC
alongside the payload.  Each entry is ``tag(1B) || length(1B) || value``.
Tags must appear in ascending order.  A TAG_END (0xFF) entry terminates the
metadata before the payload.

Tags (from Tesla's vehicle-command ``signatures.proto`` Tag enum):
  - 0x00: signature_type (1 byte — SignatureType enum value)
  - 0x01: domain (1 byte — numeric Domain enum value, e.g. 3 for INFOTAINMENT)
  - 0x02: personalization (variable-length — VIN string)
  - 0x03: epoch (variable-length bytes from vehicle)
  - 0x04: expires_at (4 bytes, big-endian uint32 — seconds since Unix epoch)
  - 0x05: counter (4 bytes, big-endian uint32 — anti-replay)
  - 0x06: challenge (variable-length — BLE challenge, not used for REST)
  - 0x07: flags (4 bytes, big-endian uint32)
  - 0xFF: end (0 bytes — terminates metadata)
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tescmd.protocol.protobuf.messages import Domain

# TLV tag constants (from signatures.proto Tag enum)
TAG_SIGNATURE_TYPE = 0x00
TAG_DOMAIN = 0x01
TAG_PERSONALIZATION = 0x02
TAG_EPOCH = 0x03
TAG_EXPIRES_AT = 0x04
TAG_COUNTER = 0x05
TAG_CHALLENGE = 0x06
TAG_FLAGS = 0x07
TAG_END = 0xFF

# SignatureType values (from signatures.proto SignatureType enum)
SIGNATURE_TYPE_HMAC_PERSONALIZED = 8


def encode_tlv(tag: int, value: bytes) -> bytes:
    """Encode a single TLV entry: tag(1B) || length(1B) || value."""
    if len(value) > 255:
        raise ValueError(f"TLV value too long ({len(value)} bytes, max 255)")
    return bytes([tag, len(value)]) + value


def encode_metadata(
    *,
    epoch: bytes,
    expires_at: int,
    counter: int,
    domain: Domain,
    vin: str,
    flags: int = 0,
) -> bytes:
    """Encode the full metadata block as a sequence of TLV entries.

    The metadata is fed into the HMAC hash alongside the command payload.
    Tags must appear in ascending order and are terminated by TAG_END.

    Parameters
    ----------
    epoch:
        Session epoch identifier (variable-length bytes from vehicle).
    expires_at:
        Command expiration time (seconds since Unix epoch).
    counter:
        Monotonically increasing counter for anti-replay.
    domain:
        The routing domain (VCSEC or INFOTAINMENT).
    vin:
        The vehicle identification number (17 chars).
    flags:
        Optional flags (default 0).

    Returns
    -------
    bytes
        Concatenated TLV entries (TAG_END is NOT included — the signer
        adds a bare 0xFF separator between metadata and payload).
    """
    parts = bytearray()
    parts.extend(encode_tlv(TAG_SIGNATURE_TYPE, bytes([SIGNATURE_TYPE_HMAC_PERSONALIZED])))
    # Domain is encoded as a single byte (numeric enum value), matching the Go SDK:
    #   meta.Add(TAG_DOMAIN, []byte{byte(x.Domain)})
    parts.extend(encode_tlv(TAG_DOMAIN, bytes([int(domain)])))
    parts.extend(encode_tlv(TAG_PERSONALIZATION, vin.encode()))
    parts.extend(encode_tlv(TAG_EPOCH, epoch))
    parts.extend(encode_tlv(TAG_EXPIRES_AT, struct.pack(">I", expires_at)))
    parts.extend(encode_tlv(TAG_COUNTER, struct.pack(">I", counter)))
    if flags:
        parts.extend(encode_tlv(TAG_FLAGS, struct.pack(">I", flags)))
    # NOTE: TAG_END is NOT included here.  The Go SDK's Checksum() writes a
    # bare 0xFF byte (no length byte) between metadata and payload when
    # computing the HMAC.  compute_hmac_tag() handles this separator.
    return bytes(parts)


def decode_metadata(data: bytes) -> dict[int, bytes]:
    """Decode a TLV metadata block into a {tag: value} dict."""
    result: dict[int, bytes] = {}
    pos = 0
    while pos < len(data):
        if pos + 2 > len(data):
            break
        tag = data[pos]
        length = data[pos + 1]
        pos += 2
        if pos + length > len(data):
            break
        result[tag] = data[pos : pos + length]
        pos += length
    return result
