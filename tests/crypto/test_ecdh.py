"""Tests for ECDH key exchange session key derivation."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from tescmd.crypto.ecdh import derive_session_key, get_uncompressed_public_key


@pytest.fixture()
def client_key() -> ec.EllipticCurvePrivateKey:
    """Generate a fresh EC P-256 private key for the 'client' side."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture()
def vehicle_key() -> ec.EllipticCurvePrivateKey:
    """Generate a fresh EC P-256 private key for the 'vehicle' side."""
    return ec.generate_private_key(ec.SECP256R1())


class TestGetUncompressedPublicKey:
    def test_get_uncompressed_public_key_length(
        self, client_key: ec.EllipticCurvePrivateKey
    ) -> None:
        pub = get_uncompressed_public_key(client_key)
        assert len(pub) == 65

    def test_get_uncompressed_public_key_prefix(
        self, client_key: ec.EllipticCurvePrivateKey
    ) -> None:
        pub = get_uncompressed_public_key(client_key)
        assert pub[0] == 0x04

    def test_get_uncompressed_public_key_deterministic(
        self, client_key: ec.EllipticCurvePrivateKey
    ) -> None:
        pub1 = get_uncompressed_public_key(client_key)
        pub2 = get_uncompressed_public_key(client_key)
        assert pub1 == pub2


class TestDeriveSessionKey:
    def test_derive_session_key_length(
        self,
        client_key: ec.EllipticCurvePrivateKey,
        vehicle_key: ec.EllipticCurvePrivateKey,
    ) -> None:
        vehicle_pub_bytes = get_uncompressed_public_key(vehicle_key)
        session_key = derive_session_key(client_key, vehicle_pub_bytes)
        assert len(session_key) == 16

    def test_derive_session_key_deterministic(
        self,
        client_key: ec.EllipticCurvePrivateKey,
        vehicle_key: ec.EllipticCurvePrivateKey,
    ) -> None:
        vehicle_pub_bytes = get_uncompressed_public_key(vehicle_key)
        key1 = derive_session_key(client_key, vehicle_pub_bytes)
        key2 = derive_session_key(client_key, vehicle_pub_bytes)
        assert key1 == key2

    def test_derive_session_key_symmetric(
        self,
        client_key: ec.EllipticCurvePrivateKey,
        vehicle_key: ec.EllipticCurvePrivateKey,
    ) -> None:
        """Both sides of the ECDH exchange must derive the same session key."""
        client_pub_bytes = get_uncompressed_public_key(client_key)
        vehicle_pub_bytes = get_uncompressed_public_key(vehicle_key)

        key_from_client = derive_session_key(client_key, vehicle_pub_bytes)
        key_from_vehicle = derive_session_key(vehicle_key, client_pub_bytes)
        assert key_from_client == key_from_vehicle

    def test_derive_session_key_different_keys(
        self, vehicle_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """Different client keys must produce different session keys."""
        other_key = ec.generate_private_key(ec.SECP256R1())
        vehicle_pub_bytes = get_uncompressed_public_key(vehicle_key)

        key1 = derive_session_key(ec.generate_private_key(ec.SECP256R1()), vehicle_pub_bytes)
        key2 = derive_session_key(other_key, vehicle_pub_bytes)
        assert key1 != key2

    def test_derive_session_key_invalid_pubkey(
        self, client_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """Invalid public key bytes must raise an error."""
        invalid_bytes = b"\x00" * 65
        with pytest.raises((ValueError, Exception)):
            derive_session_key(client_key, invalid_bytes)
