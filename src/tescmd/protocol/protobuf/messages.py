"""Minimal protobuf message definitions for Tesla Vehicle Command Protocol.

These are hand-written dataclasses with ``serialize()`` and ``parse()``
methods that produce wire-compatible bytes using ``google.protobuf``.
When full ``.proto`` generation is available, these can be replaced by the
generated ``_pb2`` modules.

Wire format reference:
  - Tesla vehicle-command proto definitions
  - https://github.com/teslamotors/vehicle-command
"""

from __future__ import annotations

import contextlib
import enum
import struct
from dataclasses import dataclass
from typing import Any

from google.protobuf import descriptor_pb2, message  # noqa: F401

# ---------------------------------------------------------------------------
# Domain enum — matches Universal_message.proto → Domain
# ---------------------------------------------------------------------------


class Domain(enum.IntEnum):
    """Routing domain for RoutableMessage."""

    DOMAIN_BROADCAST = 0
    DOMAIN_VEHICLE_SECURITY = 2  # VCSEC — lock/unlock/key
    DOMAIN_INFOTAINMENT = 3  # Car-Server — charge/climate/media


class OperationStatus(enum.IntEnum):
    """Operation status from MessageStatus (universal_message.proto)."""

    OPERATIONSTATUS_OK = 0
    OPERATIONSTATUS_WAIT = 1
    OPERATIONSTATUS_ERROR = 2


class MessageFault(enum.IntEnum):
    """Vehicle command protocol fault codes (universal_message.proto)."""

    ERROR_NONE = 0
    ERROR_BUSY = 1
    ERROR_TIMEOUT = 2
    ERROR_UNKNOWN_KEY_ID = 3
    ERROR_INACTIVE_KEY = 4
    ERROR_INVALID_SIGNATURE = 5
    ERROR_INVALID_TOKEN_OR_COUNTER = 6
    ERROR_INSUFFICIENT_PRIVILEGES = 7
    ERROR_INVALID_DOMAINS = 8
    ERROR_INVALID_COMMAND = 9
    ERROR_DECODING = 10
    ERROR_INTERNAL = 11
    ERROR_WRONG_PERSONALIZATION = 12
    ERROR_BAD_PARAMETER = 13
    ERROR_KEYCHAIN_IS_FULL = 14
    ERROR_INCORRECT_EPOCH = 15
    ERROR_IV_INCORRECT_LENGTH = 16
    ERROR_TIME_EXPIRED = 17
    ERROR_NOT_PROVISIONED_WITH_IDENTITY = 18
    ERROR_COULD_NOT_HASH_METADATA = 19
    ERROR_TIME_TO_LIVE_TOO_LONG = 20
    ERROR_REMOTE_ACCESS_DISABLED = 21
    ERROR_REMOTE_SERVICE_ACCESS_DISABLED = 22
    ERROR_COMMAND_REQUIRES_ACCOUNT_CREDENTIALS = 23
    ERROR_REQUEST_MTU_EXCEEDED = 24
    ERROR_RESPONSE_MTU_EXCEEDED = 25
    ERROR_REPEATED_COUNTER = 26
    ERROR_INVALID_KEY_HANDLE = 27
    ERROR_REQUIRES_RESPONSE_ENCRYPTION = 28


# Faults that indicate a transient problem — retry after a short delay.
TRANSIENT_FAULTS: frozenset[MessageFault] = frozenset(
    {
        MessageFault.ERROR_BUSY,
        MessageFault.ERROR_TIMEOUT,
        MessageFault.ERROR_INTERNAL,
    }
)

# Faults that indicate the key is not recognized / enrolled.
KEY_FAULTS: frozenset[MessageFault] = frozenset(
    {
        MessageFault.ERROR_UNKNOWN_KEY_ID,
        MessageFault.ERROR_INACTIVE_KEY,
    }
)

# Human-readable descriptions for common faults.
FAULT_DESCRIPTIONS: dict[MessageFault, str] = {
    MessageFault.ERROR_NONE: "No error",
    MessageFault.ERROR_BUSY: "Vehicle subsystem is busy (try again)",
    MessageFault.ERROR_TIMEOUT: "Vehicle subsystem did not respond (try again)",
    MessageFault.ERROR_UNKNOWN_KEY_ID: (
        "Vehicle does not recognize this key — run 'tescmd key enroll'"
    ),
    MessageFault.ERROR_INACTIVE_KEY: "Key has been disabled on this vehicle",
    MessageFault.ERROR_INVALID_SIGNATURE: "Invalid signature — session may be stale",
    MessageFault.ERROR_INVALID_TOKEN_OR_COUNTER: (
        "Anti-replay counter mismatch — session may be stale"
    ),
    MessageFault.ERROR_INSUFFICIENT_PRIVILEGES: "Insufficient privileges for this command",
    MessageFault.ERROR_INVALID_DOMAINS: "Command addressed to unrecognized vehicle system",
    MessageFault.ERROR_INVALID_COMMAND: "Unrecognized command",
    MessageFault.ERROR_DECODING: "Vehicle could not parse the command",
    MessageFault.ERROR_INTERNAL: "Internal vehicle error (vehicle may still be booting)",
    MessageFault.ERROR_BAD_PARAMETER: "Invalid command parameter or malformed protobuf",
    MessageFault.ERROR_WRONG_PERSONALIZATION: "Command sent to wrong VIN",
    MessageFault.ERROR_KEYCHAIN_IS_FULL: "Vehicle keychain is full — delete a key first",
    MessageFault.ERROR_INCORRECT_EPOCH: "Session epoch mismatch",
    MessageFault.ERROR_TIME_EXPIRED: "Command expired — clock may be desynchronized",
    MessageFault.ERROR_REMOTE_ACCESS_DISABLED: "Vehicle owner has disabled Mobile Access",
    MessageFault.ERROR_REMOTE_SERVICE_ACCESS_DISABLED: "Remote service commands not permitted",
    MessageFault.ERROR_COMMAND_REQUIRES_ACCOUNT_CREDENTIALS: (
        "Command requires account credentials — use Fleet API"
    ),
}


# ---------------------------------------------------------------------------
# Tag constants for manual protobuf encoding
# ---------------------------------------------------------------------------

# RoutableMessage field tags (from universal_message.proto)
# NOTE: fields 1-5, 11, 16-40 are reserved in the proto definition.
_TAG_TO_DESTINATION = 6  # SubMessage — Destination
_TAG_FROM_DESTINATION = 7  # SubMessage — Destination
_TAG_PROTOBUF_MESSAGE_AS_BYTES = 10  # bytes — oneof payload
_TAG_SIGNED_MESSAGE_STATUS = 12  # SubMessage — MessageStatus
_TAG_SIGNATURE_DATA = 13  # SubMessage — Signatures.SignatureData
_TAG_SESSION_INFO_REQUEST = 14  # SubMessage — oneof payload — SessionInfoRequest
_TAG_SESSION_INFO = 15  # bytes — oneof payload — SessionInfo response
_TAG_REQUEST_UUID = 50  # bytes
_TAG_UUID = 51  # bytes
_TAG_FLAGS = 52  # uint32

# Destination field tags
_TAG_DEST_DOMAIN = 1  # enum → Domain
_TAG_DEST_ROUTING_ADDRESS = 2  # bytes

# SessionInfoRequest field tags
_TAG_SIR_PUBLIC_KEY = 1  # bytes — 65-byte uncompressed EC point

# SignatureData field tags (from signatures.proto)
_TAG_SD_SIGNER_IDENTITY = 1  # SubMessage — KeyIdentity
_TAG_SD_SESSION_INFO_TAG = 6  # SubMessage — HMAC_Signature_Data (oneof sig_type)
_TAG_SD_HMAC_TAG = 8  # SubMessage — HMAC_Personalized_Signature_Data (oneof sig_type)

# HMAC_Personalized_Signature_Data field tags (from signatures.proto)
_TAG_HMAC_EPOCH = 1  # bytes — epoch identifier
_TAG_HMAC_COUNTER = 2  # uint32 — anti-replay counter
_TAG_HMAC_EXPIRES_AT = 3  # fixed32 — seconds since epoch
_TAG_HMAC_TAG = 4  # bytes — HMAC output

# KeyIdentity field tags (from signatures.proto — field 2 is reserved)
_TAG_KI_PUBLIC_KEY = 1  # bytes — 65-byte uncompressed EC point (oneof identity_type)

# SessionInfo field tags (from signatures.proto)
_TAG_SI_COUNTER = 1  # uint32
_TAG_SI_PUBLIC_KEY = 2  # bytes
_TAG_SI_EPOCH = 3  # bytes
_TAG_SI_CLOCK_TIME = 4  # uint32


# ---------------------------------------------------------------------------
# Low-level protobuf encoding helpers
# ---------------------------------------------------------------------------


def _encode_varint(value: int) -> bytes:
    """Encode a varint (protobuf base-128)."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def _encode_tag(field_number: int, wire_type: int) -> bytes:
    """Encode a protobuf field tag."""
    return _encode_varint((field_number << 3) | wire_type)


def _encode_length_delimited(field_number: int, data: bytes) -> bytes:
    """Encode a length-delimited field (wire type 2)."""
    tag = _encode_tag(field_number, 2)
    return tag + _encode_varint(len(data)) + data


def _encode_varint_field(field_number: int, value: int) -> bytes:
    """Encode a varint field (wire type 0)."""
    tag = _encode_tag(field_number, 0)
    return tag + _encode_varint(value)


def _encode_fixed32_field(field_number: int, value: int) -> bytes:
    """Encode a fixed32 field (wire type 5)."""
    tag = _encode_tag(field_number, 5)
    return tag + struct.pack("<I", value)


def _decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a varint, returning (value, new_pos)."""
    result = 0
    shift = 0
    while pos < len(data):
        b = data[pos]
        result |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            return result, pos
        shift += 7
    raise ValueError("Truncated varint")


def _decode_field(data: bytes, pos: int) -> tuple[int, int, Any, int]:
    """Decode one protobuf field, returning (field_number, wire_type, value, new_pos)."""
    tag, pos = _decode_varint(data, pos)
    field_number = tag >> 3
    wire_type = tag & 0x07

    if wire_type == 0:  # varint
        value, pos = _decode_varint(data, pos)
        return field_number, wire_type, value, pos
    elif wire_type == 2:  # length-delimited
        length, pos = _decode_varint(data, pos)
        value = data[pos : pos + length]
        return field_number, wire_type, value, pos + length
    elif wire_type == 5:  # 32-bit
        value = struct.unpack("<I", data[pos : pos + 4])[0]
        return field_number, wire_type, value, pos + 4
    elif wire_type == 1:  # 64-bit
        value = struct.unpack("<Q", data[pos : pos + 8])[0]
        return field_number, wire_type, value, pos + 8
    else:
        raise ValueError(f"Unsupported wire type {wire_type}")


# ---------------------------------------------------------------------------
# MessageStatus — wraps fault code in RoutableMessage field 12
# ---------------------------------------------------------------------------

# MessageStatus field tags (from universal_message.proto)
_TAG_MS_OPERATION_STATUS = 1  # enum → OperationStatus_E
_TAG_MS_SIGNED_MESSAGE_FAULT = 2  # enum → MessageFault_E


@dataclass
class MessageStatus:
    """Vehicle-side status/fault code from a RoutableMessage response.

    In the protobuf schema, ``signedMessageStatus`` (field 12) is a
    ``MessageStatus`` sub-message containing:
    - ``operation_status`` (field 1) — OperationStatus_E enum
    - ``signed_message_fault`` (field 2) — MessageFault_E enum
    """

    operation_status: OperationStatus = OperationStatus.OPERATIONSTATUS_OK
    signed_message_fault: MessageFault = MessageFault.ERROR_NONE

    def serialize(self) -> bytes:
        parts = bytearray()
        if self.operation_status != OperationStatus.OPERATIONSTATUS_OK:
            parts.extend(_encode_varint_field(_TAG_MS_OPERATION_STATUS, self.operation_status))
        if self.signed_message_fault != MessageFault.ERROR_NONE:
            parts.extend(
                _encode_varint_field(_TAG_MS_SIGNED_MESSAGE_FAULT, self.signed_message_fault)
            )
        return bytes(parts)

    @staticmethod
    def parse(data: bytes) -> MessageStatus:
        """Parse MessageStatus from protobuf bytes."""
        result = MessageStatus()
        pos = 0
        while pos < len(data):
            fn, _wt, val, pos = _decode_field(data, pos)
            if fn == _TAG_MS_OPERATION_STATUS and isinstance(val, int):
                with contextlib.suppress(ValueError):
                    result.operation_status = OperationStatus(val)
            elif fn == _TAG_MS_SIGNED_MESSAGE_FAULT and isinstance(val, int):
                try:
                    result.signed_message_fault = MessageFault(val)
                except ValueError:
                    result.signed_message_fault = MessageFault.ERROR_INTERNAL
        return result


# ---------------------------------------------------------------------------
# SessionInfo — parsed from vehicle response
# ---------------------------------------------------------------------------


@dataclass
class SessionInfo:
    """Session parameters returned by the vehicle after handshake."""

    counter: int = 0
    public_key: bytes = b""
    epoch: bytes = b""
    clock_time: int = 0

    @staticmethod
    def parse(data: bytes) -> SessionInfo:
        """Parse SessionInfo from protobuf bytes."""
        info = SessionInfo()
        pos = 0
        while pos < len(data):
            fn, _wt, val, pos = _decode_field(data, pos)
            if fn == _TAG_SI_COUNTER:
                info.counter = val
            elif fn == _TAG_SI_PUBLIC_KEY:
                info.public_key = val
            elif fn == _TAG_SI_EPOCH:
                info.epoch = val
            elif fn == _TAG_SI_CLOCK_TIME:
                info.clock_time = val
        return info


# ---------------------------------------------------------------------------
# Destination — part of RoutableMessage
# ---------------------------------------------------------------------------


@dataclass
class Destination:
    """Routing destination within a RoutableMessage."""

    domain: Domain = Domain.DOMAIN_BROADCAST
    routing_address: bytes = b""

    def serialize(self) -> bytes:
        parts = bytearray()
        if self.domain != Domain.DOMAIN_BROADCAST:
            parts.extend(_encode_varint_field(_TAG_DEST_DOMAIN, self.domain))
        if self.routing_address:
            parts.extend(_encode_length_delimited(_TAG_DEST_ROUTING_ADDRESS, self.routing_address))
        return bytes(parts)


# ---------------------------------------------------------------------------
# SessionInfoRequest — sent to initiate ECDH handshake
# ---------------------------------------------------------------------------


@dataclass
class SessionInfoRequest:
    """Request to establish an ECDH session."""

    public_key: bytes = b""

    def serialize(self) -> bytes:
        if self.public_key:
            return _encode_length_delimited(_TAG_SIR_PUBLIC_KEY, self.public_key)
        return b""


# ---------------------------------------------------------------------------
# HMAC_PersonalizedData — authentication tag
# ---------------------------------------------------------------------------


@dataclass
class HMACPersonalizedData:
    """HMAC authentication data within SignatureData."""

    epoch: bytes = b""
    counter: int = 0
    expires_at: int = 0
    tag: bytes = b""

    def serialize(self) -> bytes:
        parts = bytearray()
        if self.epoch:
            parts.extend(_encode_length_delimited(_TAG_HMAC_EPOCH, self.epoch))
        if self.counter:
            parts.extend(_encode_varint_field(_TAG_HMAC_COUNTER, self.counter))
        if self.expires_at:
            parts.extend(_encode_fixed32_field(_TAG_HMAC_EXPIRES_AT, self.expires_at))
        if self.tag:
            parts.extend(_encode_length_delimited(_TAG_HMAC_TAG, self.tag))
        return bytes(parts)

    @staticmethod
    def parse(data: bytes) -> HMACPersonalizedData:
        """Parse HMACPersonalizedData from protobuf bytes."""
        result = HMACPersonalizedData()
        pos = 0
        while pos < len(data):
            fn, _wt, val, pos = _decode_field(data, pos)
            if fn == _TAG_HMAC_EPOCH and isinstance(val, bytes):
                result.epoch = val
            elif fn == _TAG_HMAC_COUNTER and isinstance(val, int):
                result.counter = val
            elif fn == _TAG_HMAC_EXPIRES_AT and isinstance(val, int):
                result.expires_at = val
            elif fn == _TAG_HMAC_TAG and isinstance(val, bytes):
                result.tag = val
        return result


# ---------------------------------------------------------------------------
# KeyIdentity — identifies the signing key
# ---------------------------------------------------------------------------


@dataclass
class KeyIdentity:
    """Identifies the client public key for the vehicle."""

    public_key: bytes = b""

    def serialize(self) -> bytes:
        if self.public_key:
            return _encode_length_delimited(_TAG_KI_PUBLIC_KEY, self.public_key)
        return b""


# ---------------------------------------------------------------------------
# SignatureData — wraps HMAC auth for RoutableMessage
# ---------------------------------------------------------------------------


@dataclass
class SignatureData:
    """Signature/authentication data for a RoutableMessage."""

    signer_identity: KeyIdentity | None = None
    hmac_personalized_data: HMACPersonalizedData | None = None
    session_info_tag: HMACPersonalizedData | None = None

    def serialize(self) -> bytes:
        parts = bytearray()
        if self.signer_identity:
            parts.extend(
                _encode_length_delimited(_TAG_SD_SIGNER_IDENTITY, self.signer_identity.serialize())
            )
        if self.hmac_personalized_data:
            parts.extend(
                _encode_length_delimited(_TAG_SD_HMAC_TAG, self.hmac_personalized_data.serialize())
            )
        if self.session_info_tag:
            parts.extend(
                _encode_length_delimited(
                    _TAG_SD_SESSION_INFO_TAG, self.session_info_tag.serialize()
                )
            )
        return bytes(parts)

    @staticmethod
    def parse(data: bytes) -> SignatureData:
        """Parse SignatureData from protobuf bytes."""
        result = SignatureData()
        pos = 0
        while pos < len(data):
            fn, _wt, val, pos = _decode_field(data, pos)
            if fn == _TAG_SD_HMAC_TAG and isinstance(val, bytes):
                result.hmac_personalized_data = HMACPersonalizedData.parse(val)
            elif fn == _TAG_SD_SESSION_INFO_TAG and isinstance(val, bytes):
                result.session_info_tag = HMACPersonalizedData.parse(val)
        return result


# ---------------------------------------------------------------------------
# RoutableMessage — top-level envelope
# ---------------------------------------------------------------------------


@dataclass
class RoutableMessage:
    """Top-level protobuf envelope for the Vehicle Command Protocol."""

    to_destination: Destination | None = None
    from_destination: Destination | None = None
    protobuf_message_as_bytes: bytes = b""
    session_info: bytes = b""
    message_status: MessageStatus | None = None
    session_info_request: SessionInfoRequest | None = None
    signature_data: SignatureData | None = None
    request_uuid: bytes = b""
    uuid: bytes = b""
    flags: int = 0

    @property
    def signed_message_fault(self) -> MessageFault:
        """Convenience: extract the fault code from message_status."""
        if self.message_status is not None:
            return self.message_status.signed_message_fault
        return MessageFault.ERROR_NONE

    def serialize(self) -> bytes:
        """Serialize to protobuf wire format."""
        parts = bytearray()

        if self.to_destination:
            parts.extend(
                _encode_length_delimited(_TAG_TO_DESTINATION, self.to_destination.serialize())
            )
        if self.from_destination:
            parts.extend(
                _encode_length_delimited(_TAG_FROM_DESTINATION, self.from_destination.serialize())
            )
        if self.protobuf_message_as_bytes:
            parts.extend(
                _encode_length_delimited(
                    _TAG_PROTOBUF_MESSAGE_AS_BYTES, self.protobuf_message_as_bytes
                )
            )
        if self.session_info:
            parts.extend(_encode_length_delimited(_TAG_SESSION_INFO, self.session_info))
        if self.message_status is not None:
            ms_bytes = self.message_status.serialize()
            if ms_bytes:
                parts.extend(_encode_length_delimited(_TAG_SIGNED_MESSAGE_STATUS, ms_bytes))
        if self.session_info_request:
            parts.extend(
                _encode_length_delimited(
                    _TAG_SESSION_INFO_REQUEST, self.session_info_request.serialize()
                )
            )
        if self.signature_data:
            parts.extend(
                _encode_length_delimited(_TAG_SIGNATURE_DATA, self.signature_data.serialize())
            )
        if self.request_uuid:
            parts.extend(_encode_length_delimited(_TAG_REQUEST_UUID, self.request_uuid))
        if self.uuid:
            parts.extend(_encode_length_delimited(_TAG_UUID, self.uuid))
        if self.flags:
            parts.extend(_encode_varint_field(_TAG_FLAGS, self.flags))

        return bytes(parts)

    @staticmethod
    def parse(data: bytes) -> RoutableMessage:
        """Parse a RoutableMessage from protobuf bytes.

        Only extracts fields needed for session handshake response.
        """
        msg = RoutableMessage()
        pos = 0
        while pos < len(data):
            fn, _wt, val, pos = _decode_field(data, pos)
            if fn == _TAG_SESSION_INFO and isinstance(val, bytes):
                msg.session_info = val
            elif fn == _TAG_SIGNED_MESSAGE_STATUS and isinstance(val, bytes):
                msg.message_status = MessageStatus.parse(val)
            elif fn == _TAG_SIGNATURE_DATA and isinstance(val, bytes):
                msg.signature_data = SignatureData.parse(val)
            elif fn == _TAG_REQUEST_UUID and isinstance(val, bytes):
                msg.request_uuid = val
            elif fn == _TAG_UUID and isinstance(val, bytes):
                msg.uuid = val
            elif fn == _TAG_PROTOBUF_MESSAGE_AS_BYTES and isinstance(val, bytes):
                msg.protobuf_message_as_bytes = val
        return msg
