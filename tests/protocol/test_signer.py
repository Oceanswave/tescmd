"""Tests for HMAC-SHA256 command signing (tescmd.protocol.signer)."""

from __future__ import annotations

import hashlib
import hmac

from tescmd.protocol.signer import (
    compute_hmac_tag,
    derive_session_info_key,
    derive_signing_key,
    verify_session_info_tag,
)

# ---------------------------------------------------------------------------
# derive_signing_key
# ---------------------------------------------------------------------------


def test_derive_signing_key_deterministic() -> None:
    """Same session key must always produce the same signing key."""
    key = b"session-key-abc"
    assert derive_signing_key(key) == derive_signing_key(key)


def test_derive_signing_key_different_keys() -> None:
    """Different session keys must produce different signing keys."""
    key_a = b"session-key-one"
    key_b = b"session-key-two"
    assert derive_signing_key(key_a) != derive_signing_key(key_b)


def test_derive_signing_key_length() -> None:
    """Signing key must be 32 bytes (SHA-256 digest length)."""
    key = b"any-session-key"
    assert len(derive_signing_key(key)) == 32


# ---------------------------------------------------------------------------
# derive_session_info_key
# ---------------------------------------------------------------------------


def test_derive_session_info_key_deterministic() -> None:
    """Same session key must always produce the same session info key."""
    key = b"session-key-xyz"
    assert derive_session_info_key(key) == derive_session_info_key(key)


def test_derive_session_info_key_different_from_signing() -> None:
    """Session info key and signing key derived from the same session key must differ."""
    key = b"shared-session-key"
    assert derive_session_info_key(key) != derive_signing_key(key)


# ---------------------------------------------------------------------------
# compute_hmac_tag
# ---------------------------------------------------------------------------


def test_compute_hmac_tag_full_length() -> None:
    """HMAC tag must always be the full 32-byte SHA-256 output."""
    signing_key = derive_signing_key(b"test-session")
    metadata = b"\x01\x02\x03"
    payload = b"\x0a\x0b\x0c"
    tag = compute_hmac_tag(signing_key, metadata, payload)
    assert len(tag) == 32


def test_compute_hmac_tag_deterministic() -> None:
    """Same inputs must always produce the same tag."""
    signing_key = derive_signing_key(b"deterministic-session")
    metadata = b"\xaa\xbb"
    payload = b"\xcc\xdd"
    tag_a = compute_hmac_tag(signing_key, metadata, payload)
    tag_b = compute_hmac_tag(signing_key, metadata, payload)
    assert tag_a == tag_b


def test_compute_hmac_tag_different_payload() -> None:
    """Different payloads must produce different tags."""
    signing_key = derive_signing_key(b"payload-diff-session")
    metadata = b"\x00"
    tag_a = compute_hmac_tag(signing_key, metadata, b"payload-one")
    tag_b = compute_hmac_tag(signing_key, metadata, b"payload-two")
    assert tag_a != tag_b


# ---------------------------------------------------------------------------
# verify_session_info_tag
# ---------------------------------------------------------------------------


def test_verify_session_info_tag_valid() -> None:
    """verify_session_info_tag must return True for a correctly computed tag."""
    session_key = b"verify-session-key"
    session_info_key = derive_session_info_key(session_key)
    session_info_bytes = b"some-session-info-payload"

    # Compute the expected tag using the same algorithm the module uses.
    expected_tag = hmac.new(session_info_key, session_info_bytes, hashlib.sha256).digest()

    assert verify_session_info_tag(session_info_key, session_info_bytes, expected_tag) is True


def test_verify_session_info_tag_invalid() -> None:
    """verify_session_info_tag must return False for an incorrect tag."""
    session_key = b"verify-session-key"
    session_info_key = derive_session_info_key(session_key)
    session_info_bytes = b"some-session-info-payload"

    wrong_tag = b"\x00" * 32

    assert verify_session_info_tag(session_info_key, session_info_bytes, wrong_tag) is False
