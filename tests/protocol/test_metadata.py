"""Tests for tescmd.protocol.metadata — TLV metadata serialization."""

from __future__ import annotations

import struct

from tescmd.protocol.metadata import (
    SIGNATURE_TYPE_HMAC_PERSONALIZED,
    TAG_COUNTER,
    TAG_DOMAIN,
    TAG_EPOCH,
    TAG_EXPIRES_AT,
    TAG_FLAGS,
    TAG_PERSONALIZATION,
    TAG_SIGNATURE_TYPE,
    decode_metadata,
    encode_metadata,
    encode_tlv,
)
from tescmd.protocol.protobuf.messages import Domain

VIN = "5YJ3E1EA1NF000001"


class TestEncodeTlv:
    """Tests for encode_tlv()."""

    def test_encode_tlv_basic(self) -> None:
        """Simple tag+value produces tag(1B) || length(1B) || value."""
        result = encode_tlv(0x01, b"\xaa\xbb")
        assert result == bytes([0x01, 0x02, 0xAA, 0xBB])

    def test_encode_tlv_empty_value(self) -> None:
        """An empty value produces tag(1B) || 0x00 with no trailing bytes."""
        result = encode_tlv(0x05, b"")
        assert result == bytes([0x05, 0x00])
        assert len(result) == 2


class TestEncodeMetadata:
    """Tests for encode_metadata()."""

    def test_encode_metadata_basic(self) -> None:
        """Metadata with epoch, expires_at, counter, domain, vin (no flags)."""
        epoch = b"\x01\x02"
        expires_at = 1_700_000_000
        counter = 42

        result = encode_metadata(
            epoch=epoch,
            expires_at=expires_at,
            counter=counter,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
        )

        # Domain is a single byte (enum int value), no TAG_END in metadata.
        expected = bytearray()
        expected.extend(encode_tlv(TAG_SIGNATURE_TYPE, bytes([SIGNATURE_TYPE_HMAC_PERSONALIZED])))
        expected.extend(encode_tlv(TAG_DOMAIN, bytes([int(Domain.DOMAIN_INFOTAINMENT)])))
        expected.extend(encode_tlv(TAG_PERSONALIZATION, VIN.encode()))
        expected.extend(encode_tlv(TAG_EPOCH, epoch))
        expected.extend(encode_tlv(TAG_EXPIRES_AT, struct.pack(">I", expires_at)))
        expected.extend(encode_tlv(TAG_COUNTER, struct.pack(">I", counter)))
        assert result == bytes(expected)

    def test_encode_metadata_domain_is_single_byte(self) -> None:
        """Domain is encoded as a single byte (numeric enum value), not a string.

        The Go SDK encodes domain as: []byte{byte(x.Domain)}
        Infotainment = 3, VCSEC = 2.
        """
        result = encode_metadata(
            epoch=b"\x01",
            expires_at=100,
            counter=1,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
        )
        decoded = decode_metadata(result)
        assert decoded[TAG_DOMAIN] == bytes([3])  # DOMAIN_INFOTAINMENT = 3

    def test_encode_metadata_vcsec_domain(self) -> None:
        """VCSEC domain produces the correct single-byte value."""
        result = encode_metadata(
            epoch=b"\x01",
            expires_at=100,
            counter=1,
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            vin=VIN,
        )
        decoded = decode_metadata(result)
        assert decoded[TAG_DOMAIN] == bytes([2])  # DOMAIN_VEHICLE_SECURITY = 2

    def test_encode_metadata_with_flags(self) -> None:
        """Non-zero flags should appear as a TLV entry."""
        epoch = b"\xde\xad"
        expires_at = 1_700_000_000
        counter = 7
        flags = 0x0000_0010

        result = encode_metadata(
            epoch=epoch,
            expires_at=expires_at,
            counter=counter,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
            flags=flags,
        )

        decoded = decode_metadata(result)
        assert TAG_FLAGS in decoded
        assert struct.unpack(">I", decoded[TAG_FLAGS])[0] == flags

    def test_encode_metadata_zero_flags_omitted(self) -> None:
        """When flags=0 (default), the FLAGS tag must not appear in output."""
        result = encode_metadata(
            epoch=b"\xff",
            expires_at=100,
            counter=1,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
            flags=0,
        )

        decoded = decode_metadata(result)
        assert TAG_FLAGS not in decoded

    def test_encode_metadata_no_tag_end(self) -> None:
        """Metadata does NOT include TAG_END — the signer adds the separator.

        The Go SDK's Checksum() writes a bare 0xFF byte (no length byte)
        between metadata and payload.  encode_metadata() must not include it.
        """
        result = encode_metadata(
            epoch=b"\x01",
            expires_at=100,
            counter=1,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
        )

        decoded = decode_metadata(result)
        # TAG_END (0xFF) must not appear in the decoded fields
        assert 0xFF not in decoded

    def test_encode_metadata_tag_order(self) -> None:
        """Tags must appear in ascending numerical order."""
        result = encode_metadata(
            epoch=b"\x01\x02\x03",
            expires_at=1_700_000_000,
            counter=42,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
            flags=1,
        )

        # Extract tag bytes from the TLV stream
        tags: list[int] = []
        pos = 0
        while pos < len(result):
            tag = result[pos]
            length = result[pos + 1]
            tags.append(tag)
            pos += 2 + length

        # Verify ascending order
        assert tags == sorted(tags)


class TestDecodeMetadata:
    """Tests for decode_metadata()."""

    def test_decode_metadata_roundtrip(self) -> None:
        """Encoding then decoding recovers all original fields."""
        epoch = b"\x0a\x0b\x0c"
        expires_at = 1_710_000_000
        counter = 999

        encoded = encode_metadata(
            epoch=epoch,
            expires_at=expires_at,
            counter=counter,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
        )
        decoded = decode_metadata(encoded)

        assert decoded[TAG_SIGNATURE_TYPE] == bytes([SIGNATURE_TYPE_HMAC_PERSONALIZED])
        assert decoded[TAG_DOMAIN] == bytes([int(Domain.DOMAIN_INFOTAINMENT)])
        assert decoded[TAG_PERSONALIZATION] == VIN.encode()
        assert decoded[TAG_EPOCH] == epoch
        assert struct.unpack(">I", decoded[TAG_EXPIRES_AT])[0] == expires_at
        assert struct.unpack(">I", decoded[TAG_COUNTER])[0] == counter
        assert TAG_FLAGS not in decoded

    def test_decode_metadata_with_flags(self) -> None:
        """Roundtrip with non-zero flags recovers flags correctly."""
        epoch = b"\x01"
        expires_at = 500
        counter = 1
        flags = 0xFF

        encoded = encode_metadata(
            epoch=epoch,
            expires_at=expires_at,
            counter=counter,
            domain=Domain.DOMAIN_INFOTAINMENT,
            vin=VIN,
            flags=flags,
        )
        decoded = decode_metadata(encoded)

        assert decoded[TAG_EPOCH] == epoch
        assert struct.unpack(">I", decoded[TAG_EXPIRES_AT])[0] == expires_at
        assert struct.unpack(">I", decoded[TAG_COUNTER])[0] == counter
        assert TAG_FLAGS in decoded
        assert struct.unpack(">I", decoded[TAG_FLAGS])[0] == flags

    def test_decode_metadata_empty(self) -> None:
        """Empty input returns an empty dict."""
        assert decode_metadata(b"") == {}
