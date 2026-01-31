"""Tests for tescmd.protocol.encoder — RoutableMessage assembly and encoding."""

from __future__ import annotations

import base64
import time

from tescmd.protocol.encoder import (
    build_session_info_request,
    build_signed_command,
    default_expiry,
    encode_routable_message,
)
from tescmd.protocol.protobuf.messages import (
    Domain,
    MessageFault,
    RoutableMessage,
    _encode_length_delimited,
    _encode_varint_field,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# 65-byte uncompressed EC public key (0x04 || X || Y)
FAKE_PUBLIC_KEY = b"\x04" + b"\xab" * 32 + b"\xcd" * 32

FAKE_EPOCH = b"\x01\x02\x03\x04"
FAKE_HMAC_TAG = b"\xff" * 32
FAKE_PAYLOAD = b"\x0a\x0b\x0c"


# ---------------------------------------------------------------------------
# test_build_session_info_request_structure
# ---------------------------------------------------------------------------


class TestBuildSessionInfoRequest:
    def test_build_session_info_request_structure(self) -> None:
        msg = build_session_info_request(
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            client_public_key=FAKE_PUBLIC_KEY,
        )

        # to_destination has the correct domain
        assert msg.to_destination is not None
        assert msg.to_destination.domain == Domain.DOMAIN_VEHICLE_SECURITY

        # from_destination carries the client public key as routing_address
        assert msg.from_destination is not None
        assert msg.from_destination.routing_address == FAKE_PUBLIC_KEY

        # session_info_request contains the public key
        assert msg.session_info_request is not None
        assert msg.session_info_request.public_key == FAKE_PUBLIC_KEY

        # uuid is exactly 16 bytes
        assert isinstance(msg.uuid, bytes)
        assert len(msg.uuid) == 16


# ---------------------------------------------------------------------------
# test_build_signed_command_structure
# ---------------------------------------------------------------------------


class TestBuildSignedCommand:
    def test_build_signed_command_structure(self) -> None:
        counter = 42
        expires_at = int(time.time()) + 15

        msg = build_signed_command(
            domain=Domain.DOMAIN_INFOTAINMENT,
            payload=FAKE_PAYLOAD,
            client_public_key=FAKE_PUBLIC_KEY,
            epoch=FAKE_EPOCH,
            counter=counter,
            expires_at=expires_at,
            hmac_tag=FAKE_HMAC_TAG,
        )

        # to_destination has the correct domain
        assert msg.to_destination is not None
        assert msg.to_destination.domain == Domain.DOMAIN_INFOTAINMENT

        # from_destination carries the client public key
        assert msg.from_destination is not None
        assert msg.from_destination.routing_address == FAKE_PUBLIC_KEY

        # payload is stored verbatim
        assert msg.protobuf_message_as_bytes == FAKE_PAYLOAD

        # signature_data is fully populated
        assert msg.signature_data is not None

        sd = msg.signature_data
        assert sd.signer_identity is not None
        assert sd.signer_identity.public_key == FAKE_PUBLIC_KEY

        assert sd.hmac_personalized_data is not None
        assert sd.hmac_personalized_data.epoch == FAKE_EPOCH
        assert sd.hmac_personalized_data.counter == counter
        assert sd.hmac_personalized_data.expires_at == expires_at
        assert sd.hmac_personalized_data.tag == FAKE_HMAC_TAG

        # uuid is exactly 16 bytes
        assert isinstance(msg.uuid, bytes)
        assert len(msg.uuid) == 16


# ---------------------------------------------------------------------------
# test_encode_routable_message_base64
# ---------------------------------------------------------------------------


class TestEncodeRoutableMessage:
    def test_encode_routable_message_base64(self) -> None:
        msg = build_session_info_request(
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            client_public_key=FAKE_PUBLIC_KEY,
        )
        encoded = encode_routable_message(msg)

        # Output is a plain ASCII string (no newlines, no padding issues)
        assert isinstance(encoded, str)

        # Decoding from base64 must succeed and produce bytes
        raw = base64.b64decode(encoded)
        assert isinstance(raw, bytes)
        assert len(raw) > 0

    def test_encode_routable_message_roundtrip(self) -> None:
        """build -> serialize -> base64 -> decode -> parse -> verify payload."""
        msg = build_session_info_request(
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            client_public_key=FAKE_PUBLIC_KEY,
        )
        encoded = encode_routable_message(msg)

        # Decode base64 back to wire bytes
        raw = base64.b64decode(encoded)

        # Parse the wire bytes back into a RoutableMessage
        parsed = RoutableMessage.parse(raw)

        # The uuid field should survive the round-trip
        assert parsed.uuid == msg.uuid


# ---------------------------------------------------------------------------
# test_default_expiry
# ---------------------------------------------------------------------------


class TestDefaultExpiry:
    def test_default_expiry_zero_offset(self) -> None:
        """With zero clock_offset, expiry is still based on wall clock + TTL."""
        now = int(time.time())
        expiry = default_expiry()
        assert abs(expiry - (now + 15)) <= 2

    def test_default_expiry_custom_ttl(self) -> None:
        ttl = 120
        now = int(time.time())
        expiry = default_expiry(ttl_seconds=ttl)
        expected = now + ttl
        assert abs(expiry - expected) <= 2

    def test_default_expiry_with_clock_offset(self) -> None:
        """A negative clock_offset converts wall-clock time to epoch-relative.

        The Go SDK computes ExpiresAt = clockTime + elapsed + TTL.
        Our clock_offset = clockTime - handshake_time, so:
            now + clock_offset + TTL ≈ clockTime + TTL.
        """
        # Simulate: vehicle clock_time=300, handshake happened at now
        clock_time = 300
        local_time = int(time.time())
        clock_offset = clock_time - local_time  # large negative number

        expiry = default_expiry(clock_offset=clock_offset, ttl_seconds=15)

        # Result should be close to clock_time + TTL (small positive number)
        expected = clock_time + 15
        assert abs(expiry - expected) <= 2

    def test_default_expiry_positive_offset(self) -> None:
        """Positive clock_offset (vehicle clock ahead of local) still works."""
        now = int(time.time())
        expiry = default_expiry(clock_offset=100, ttl_seconds=15)
        expected = now + 100 + 15
        assert abs(expiry - expected) <= 2


# ---------------------------------------------------------------------------
# test_build_session_info_request_different_domains
# ---------------------------------------------------------------------------


class TestDifferentDomains:
    def test_build_session_info_request_different_domains(self) -> None:
        """VCSEC and INFOTAINMENT produce different serialized bytes."""
        msg_vcsec = build_session_info_request(
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            client_public_key=FAKE_PUBLIC_KEY,
        )
        msg_info = build_session_info_request(
            domain=Domain.DOMAIN_INFOTAINMENT,
            client_public_key=FAKE_PUBLIC_KEY,
        )

        # The uuid is random, so zero it out for a fair comparison of structure
        msg_vcsec.uuid = b"\x00" * 16
        msg_info.uuid = b"\x00" * 16

        wire_vcsec = msg_vcsec.serialize()
        wire_info = msg_info.serialize()

        # Both produce non-empty output
        assert len(wire_vcsec) > 0
        assert len(wire_info) > 0

        # The serialized bytes differ because the domain varint differs
        assert wire_vcsec != wire_info


# ---------------------------------------------------------------------------
# test_routable_message_fault_parsing
# ---------------------------------------------------------------------------


class TestRoutableMessageFaultParsing:
    """Verify RoutableMessage.parse extracts signedMessageStatus (field 12).

    In the protobuf schema, field 12 is a ``MessageStatus`` sub-message
    containing:
    - ``operation_status`` (field 1) — OperationStatus_E enum
    - ``signed_message_fault`` (field 2) — MessageFault_E enum
    """

    def _encode_message_status(self, fault_value: int) -> bytes:
        """Encode a MessageStatus sub-message at field 12."""
        inner = _encode_varint_field(2, fault_value)  # signed_message_fault = field 2
        return _encode_length_delimited(12, inner)

    def test_parse_fault_code(self) -> None:
        """A response with field 12 set parses the fault code."""
        raw = self._encode_message_status(1)  # BUSY
        msg = RoutableMessage.parse(raw)
        assert msg.signed_message_fault == MessageFault.ERROR_BUSY
        assert msg.message_status is not None
        assert msg.message_status.signed_message_fault == MessageFault.ERROR_BUSY

    def test_parse_unknown_key_fault(self) -> None:
        raw = self._encode_message_status(3)  # UNKNOWN_KEY_ID
        msg = RoutableMessage.parse(raw)
        assert msg.signed_message_fault == MessageFault.ERROR_UNKNOWN_KEY_ID

    def test_parse_timeout_fault(self) -> None:
        """TIMEOUT (2) fault code."""
        raw = self._encode_message_status(2)
        msg = RoutableMessage.parse(raw)
        assert msg.signed_message_fault == MessageFault.ERROR_TIMEOUT

    def test_parse_no_fault(self) -> None:
        """A response without field 12 defaults to ERROR_NONE."""
        msg = RoutableMessage.parse(b"")
        assert msg.signed_message_fault == MessageFault.ERROR_NONE
        assert msg.message_status is None

    def test_parse_unknown_fault_value(self) -> None:
        """An unknown fault value falls back to ERROR_INTERNAL."""
        raw = self._encode_message_status(9999)
        msg = RoutableMessage.parse(raw)
        assert msg.signed_message_fault == MessageFault.ERROR_INTERNAL

    def test_parse_real_vehicle_response(self) -> None:
        """Parse the actual hex from a real vehicle handshake response.

        The raw bytes contain a MessageStatus with:
        - operation_status = OPERATIONSTATUS_ERROR (2) at field 1
        - signed_message_fault = REQUEST_MTU_EXCEEDED (24) at field 2
        """
        raw = bytes.fromhex(
            "3243124104d33cc93fc9dd77f797e16e0542bbad0b023de3973e53"
            "ca07252f9bd9205cfb4b2ea4cbb666e26f7e089a89ccf1abb0ce43"
            "b2c10fc894988c547c705d1bbe56e33a020802620408021018"
        )
        msg = RoutableMessage.parse(raw)
        assert msg.signed_message_fault == MessageFault.ERROR_REQUEST_MTU_EXCEEDED
        assert msg.message_status is not None
        assert msg.message_status.operation_status.value == 2  # ERROR
