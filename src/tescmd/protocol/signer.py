"""HMAC-SHA256 command signing for the Vehicle Command Protocol.

Signing flow (for the REST/Fleet API path):

1. Serialize metadata as TLV: ``encode_metadata(epoch, expires_at, counter)``
2. Derive signing key: ``K' = HMAC-SHA256(K, b"authenticated command")``
3. Compute tag: ``HMAC-SHA256(K', metadata_bytes || 0xFF || payload_bytes)``
4. For VCSEC domain: truncate tag to 17 bytes.
5. Attach to ``RoutableMessage.signature_data.HMAC_PersonalizedData.tag``
"""

from __future__ import annotations

import hashlib
import hmac

from tescmd.protocol.protobuf.messages import Domain

# Derivation labels (from Tesla vehicle-command specification)
_LABEL_AUTHENTICATED_COMMAND = b"authenticated command"
_LABEL_SESSION_INFO = b"session info"

# VCSEC domain uses a truncated 17-byte tag
_VCSEC_TAG_LENGTH = 17


def derive_signing_key(session_key: bytes) -> bytes:
    """Derive the command signing key: ``HMAC-SHA256(K, "authenticated command")``."""
    return hmac.new(session_key, _LABEL_AUTHENTICATED_COMMAND, hashlib.sha256).digest()


def derive_session_info_key(session_key: bytes) -> bytes:
    """Derive the session info verification key: ``HMAC-SHA256(K, "session info")``."""
    return hmac.new(session_key, _LABEL_SESSION_INFO, hashlib.sha256).digest()


def compute_hmac_tag(
    signing_key: bytes,
    metadata_bytes: bytes,
    payload_bytes: bytes,
    *,
    domain: Domain = Domain.DOMAIN_INFOTAINMENT,
) -> bytes:
    """Compute the HMAC-SHA256 authentication tag.

    Parameters
    ----------
    signing_key:
        The derived signing key from :func:`derive_signing_key`.
    metadata_bytes:
        TLV-encoded metadata (epoch, expires_at, counter, flags).
    payload_bytes:
        The serialized protobuf command payload.
    domain:
        The routing domain — VCSEC tags are truncated to 17 bytes.

    Returns
    -------
    bytes
        The HMAC tag (32 bytes for Infotainment, 17 bytes for VCSEC).
    """
    # The Go SDK streams metadata entries into the hash, then Checksum()
    # writes a bare TAG_END byte (0xFF) before the payload — no length byte.
    #   m.Context.Write([]byte{byte(signatures.Tag_TAG_END)})  // just 0xFF
    #   m.Context.Write(message)
    msg = metadata_bytes + b"\xff" + payload_bytes
    tag = hmac.new(signing_key, msg, hashlib.sha256).digest()

    if domain == Domain.DOMAIN_VEHICLE_SECURITY:
        return tag[:_VCSEC_TAG_LENGTH]
    return tag


def verify_session_info_tag(
    session_info_key: bytes,
    session_info_bytes: bytes,
    expected_tag: bytes,
) -> bool:
    """Verify the HMAC tag on a SessionInfo response.

    Returns True if the tag is valid.
    """
    computed = hmac.new(session_info_key, session_info_bytes, hashlib.sha256).digest()
    return hmac.compare_digest(computed, expected_tag)
