"""RoutableMessage assembly and base64 encoding for the signed_command endpoint."""

from __future__ import annotations

import base64
import os
import time

from tescmd.protocol.protobuf.messages import (
    Destination,
    Domain,
    HMACPersonalizedData,
    KeyIdentity,
    RoutableMessage,
    SessionInfoRequest,
    SignatureData,
)


def build_session_info_request(
    *,
    domain: Domain,
    client_public_key: bytes,
) -> RoutableMessage:
    """Build a session handshake request message.

    Parameters
    ----------
    domain:
        Target domain (VCSEC or INFOTAINMENT).
    client_public_key:
        65-byte uncompressed EC public key (``0x04 || X || Y``).

    Returns
    -------
    RoutableMessage
        Ready to serialize → base64 → POST.
    """
    return RoutableMessage(
        to_destination=Destination(domain=domain),
        from_destination=Destination(routing_address=client_public_key),
        session_info_request=SessionInfoRequest(public_key=client_public_key),
        uuid=os.urandom(16),
    )


def build_signed_command(
    *,
    domain: Domain,
    payload: bytes,
    client_public_key: bytes,
    epoch: bytes,
    counter: int,
    expires_at: int,
    hmac_tag: bytes,
) -> RoutableMessage:
    """Build a signed command message.

    Parameters
    ----------
    domain:
        Target domain (VCSEC or INFOTAINMENT).
    payload:
        Serialized protobuf command (Action or UnsignedMessage).
    client_public_key:
        65-byte uncompressed client public key.
    epoch:
        Session epoch identifier from handshake.
    counter:
        Monotonically increasing counter.
    expires_at:
        Command expiration in vehicle epoch-relative seconds.
    hmac_tag:
        Computed HMAC-SHA256 tag from :func:`~tescmd.protocol.signer.compute_hmac_tag`.

    Returns
    -------
    RoutableMessage
        Ready to serialize → base64 → POST.
    """
    return RoutableMessage(
        to_destination=Destination(domain=domain),
        from_destination=Destination(routing_address=client_public_key),
        protobuf_message_as_bytes=payload,
        signature_data=SignatureData(
            signer_identity=KeyIdentity(public_key=client_public_key),
            hmac_personalized_data=HMACPersonalizedData(
                epoch=epoch,
                counter=counter,
                expires_at=expires_at,
                tag=hmac_tag,
            ),
        ),
        uuid=os.urandom(16),
    )


def encode_routable_message(msg: RoutableMessage) -> str:
    """Serialize and base64-encode a RoutableMessage for the API."""
    return base64.b64encode(msg.serialize()).decode("ascii")


def default_expiry(clock_offset: int = 0, ttl_seconds: int = 15) -> int:
    """Return a command expiry timestamp in the vehicle's epoch-relative time.

    The Go SDK computes ``ExpiresAt = clockTime + elapsed + TTL`` where
    ``clockTime`` comes from the vehicle's SessionInfo.  Our Session stores
    ``clock_offset = clockTime - local_time_at_handshake``, so::

        expires_at = now + clock_offset + TTL
                   = now + (clockTime - handshake_time) + TTL
                   ≈ clockTime + TTL   (when sent shortly after handshake)

    Parameters
    ----------
    clock_offset:
        ``session.clock_offset`` — the difference between the vehicle's
        epoch clock and the local wall clock at handshake time.
    ttl_seconds:
        Time-to-live in seconds (default 15).
    """
    return int(time.time()) + clock_offset + ttl_seconds
