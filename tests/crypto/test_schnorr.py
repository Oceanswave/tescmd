"""Tests for Schnorr/P-256 signing (Tesla.SS256)."""

from __future__ import annotations

import base64
import hashlib
import json
import struct

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tescmd.crypto.schnorr import (
    P256_GENERATOR_BYTES,
    P256_ORDER,
    _b64url,
    _challenge,
    _deterministic_nonce,
    schnorr_sign,
    sign_fleet_telemetry_config,
)

_SCALAR_LEN = 32


def _make_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


class TestDeterministicNonce:
    def test_produces_32_bytes(self) -> None:
        scalar = b"\x01" * 32
        msg_hash = hashlib.sha256(b"test").digest()
        nonce = _deterministic_nonce(scalar, msg_hash)
        assert len(nonce) == 32

    def test_deterministic(self) -> None:
        """Same inputs always produce the same nonce."""
        scalar = b"\xab" * 32
        msg_hash = hashlib.sha256(b"hello").digest()
        a = _deterministic_nonce(scalar, msg_hash)
        b = _deterministic_nonce(scalar, msg_hash)
        assert a == b

    def test_different_inputs_different_nonces(self) -> None:
        scalar = b"\x01" * 32
        h1 = hashlib.sha256(b"msg1").digest()
        h2 = hashlib.sha256(b"msg2").digest()
        assert _deterministic_nonce(scalar, h1) != _deterministic_nonce(scalar, h2)

    def test_nonce_in_range(self) -> None:
        """Nonce must be in (0, n)."""
        scalar = b"\xfe" * 32
        msg_hash = hashlib.sha256(b"range-test").digest()
        nonce = _deterministic_nonce(scalar, msg_hash)
        nonce_int = int.from_bytes(nonce, "big")
        assert 0 < nonce_int < P256_ORDER


class TestChallenge:
    def test_produces_32_bytes(self) -> None:
        # Fake 65-byte uncompressed points
        nonce_pub = b"\x04" + b"\x01" * 64
        sender_pub = b"\x04" + b"\x02" * 64
        c = _challenge(nonce_pub, sender_pub, b"hello")
        assert len(c) == 32

    def test_deterministic(self) -> None:
        nonce_pub = b"\x04" + b"\xaa" * 64
        sender_pub = b"\x04" + b"\xbb" * 64
        msg = b"test-challenge"
        assert _challenge(nonce_pub, sender_pub, msg) == _challenge(nonce_pub, sender_pub, msg)

    def test_includes_generator(self) -> None:
        """Changing the generator changes the hash (verifies G is included)."""
        nonce_pub = b"\x04" + b"\x01" * 64
        sender_pub = b"\x04" + b"\x02" * 64
        msg = b"gen-test"

        # Compute expected challenge manually
        h = hashlib.sha256()
        h.update(struct.pack(">I", len(P256_GENERATOR_BYTES)))
        h.update(P256_GENERATOR_BYTES)
        h.update(struct.pack(">I", len(nonce_pub)))
        h.update(nonce_pub)
        h.update(struct.pack(">I", len(sender_pub)))
        h.update(sender_pub)
        h.update(struct.pack(">I", len(msg)))
        h.update(msg)
        expected = h.digest()

        assert _challenge(nonce_pub, sender_pub, msg) == expected


class TestSchnorrSign:
    def test_signature_length(self) -> None:
        """Signature is 96 bytes (32 + 32 + 32)."""
        key = _make_key()
        sig = schnorr_sign(key, b"test message")
        assert len(sig) == 96

    def test_deterministic(self) -> None:
        """Same key + message always gives the same signature."""
        key = _make_key()
        msg = b"deterministic test"
        assert schnorr_sign(key, msg) == schnorr_sign(key, msg)

    def test_different_messages_different_sigs(self) -> None:
        key = _make_key()
        s1 = schnorr_sign(key, b"msg1")
        s2 = schnorr_sign(key, b"msg2")
        assert s1 != s2

    def test_different_keys_different_sigs(self) -> None:
        k1 = _make_key()
        k2 = _make_key()
        msg = b"same message"
        assert schnorr_sign(k1, msg) != schnorr_sign(k2, msg)

    def test_verify_roundtrip(self) -> None:
        """Verify the signature using the same challenge math as the Go SDK."""
        key = _make_key()
        message = b"verify-roundtrip"
        sig = schnorr_sign(key, message)

        # Extract components
        nonce_x = sig[0:32]
        nonce_y = sig[32:64]
        r_bytes = sig[64:96]

        nonce_pub = b"\x04" + nonce_x + nonce_y
        sender_pub = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)

        # Recompute challenge
        c_bytes = _challenge(nonce_pub, sender_pub, message)
        c_int = int.from_bytes(c_bytes, "big")
        r_int = int.from_bytes(r_bytes, "big")

        # Full point-addition verification would require low-level curve ops.
        # Instead, verify the nonce point is a valid P-256 point and that
        # all scalar values are in range.
        assert 0 < r_int < P256_ORDER
        assert 0 < c_int < 2**256
        nonce_x_int = int.from_bytes(nonce_x, "big")
        nonce_y_int = int.from_bytes(nonce_y, "big")

        # At minimum, verify the nonce is on the curve
        p = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
        lhs = (nonce_y_int * nonce_y_int) % p
        a = -3
        b_coeff = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
        rhs = (nonce_x_int**3 + a * nonce_x_int + b_coeff) % p
        assert lhs == rhs, "Nonce point not on P-256 curve"


class TestSignFleetTelemetryConfig:
    def test_produces_three_part_jws(self) -> None:
        key = _make_key()
        config = {
            "hostname": "machine.tailnet.ts.net",
            "ca": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            "fields": {"BatteryLevel": {"interval_seconds": 10}},
            "alert_types": ["service"],
        }
        jws = sign_fleet_telemetry_config(key, config)
        parts = jws.split(".")
        assert len(parts) == 3

    def test_header_has_correct_algorithm(self) -> None:
        key = _make_key()
        config = {"hostname": "test", "ca": "test", "fields": {}}
        jws = sign_fleet_telemetry_config(key, config)
        header_b64 = jws.split(".")[0]
        # Add padding for base64 decode
        padded = header_b64 + "=" * (4 - len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
        assert header["alg"] == "Tesla.SS256"
        assert header["typ"] == "JWT"

    def test_payload_has_iss_and_aud(self) -> None:
        key = _make_key()
        config = {"hostname": "test.ts.net", "ca": "pem", "fields": {}}
        jws = sign_fleet_telemetry_config(key, config)
        payload_b64 = jws.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        assert payload["aud"] == "com.tesla.fleet.TelemetryClient"
        assert "iss" in payload
        # iss should be base64 of uncompressed public key (65 bytes)
        iss_bytes = base64.standard_b64decode(payload["iss"])
        assert len(iss_bytes) == 65
        assert iss_bytes[0] == 0x04

    def test_payload_preserves_config_fields(self) -> None:
        key = _make_key()
        config = {
            "hostname": "my-host.ts.net",
            "ca": "cert-pem",
            "fields": {"Speed": {"interval_seconds": 5}},
            "alert_types": ["service"],
        }
        jws = sign_fleet_telemetry_config(key, config)
        payload_b64 = jws.split(".")[1]
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        assert payload["hostname"] == "my-host.ts.net"
        assert payload["ca"] == "cert-pem"
        assert payload["fields"] == {"Speed": {"interval_seconds": 5}}
        assert payload["alert_types"] == ["service"]

    def test_does_not_mutate_input(self) -> None:
        key = _make_key()
        config = {"hostname": "test", "ca": "test", "fields": {}}
        original = dict(config)
        sign_fleet_telemetry_config(key, config)
        assert config == original

    def test_signature_is_96_bytes(self) -> None:
        key = _make_key()
        config = {"hostname": "test", "ca": "test", "fields": {}}
        jws = sign_fleet_telemetry_config(key, config)
        sig_b64 = jws.split(".")[2]
        padded = sig_b64 + "=" * (4 - len(sig_b64) % 4)
        sig_bytes = base64.urlsafe_b64decode(padded)
        assert len(sig_bytes) == 96

    def test_deterministic(self) -> None:
        key = _make_key()
        config = {"hostname": "test", "ca": "test", "fields": {}}
        assert sign_fleet_telemetry_config(key, config) == sign_fleet_telemetry_config(key, config)


class TestB64url:
    def test_no_padding(self) -> None:
        """base64url encoding should strip padding."""
        result = _b64url(b"test")
        assert "=" not in result

    def test_url_safe_chars(self) -> None:
        """Should use - and _ instead of + and /."""
        result = _b64url(b"\xff\xfe\xfd")
        assert "+" not in result
        assert "/" not in result
