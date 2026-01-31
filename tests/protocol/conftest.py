"""Shared fixtures for protocol tests."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


@pytest.fixture
def ec_key_pair() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    """Generate a fresh EC P-256 key pair for testing.

    Returns (private_key, uncompressed_public_key_bytes).
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_bytes = private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    return private_key, public_bytes


@pytest.fixture
def client_private_key() -> ec.EllipticCurvePrivateKey:
    """A deterministic client private key for session tests."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def vehicle_private_key() -> ec.EllipticCurvePrivateKey:
    """A deterministic vehicle private key for session tests."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def sample_epoch() -> bytes:
    """A sample epoch identifier."""
    return b"\x01\x02\x03\x04"


@pytest.fixture
def sample_session_key() -> bytes:
    """A 16-byte session key for signer tests."""
    return b"\xaa" * 16
