"""Schnorr signatures over NIST P-256 for Tesla Fleet Telemetry JWS.

Implements the ``Tesla.SS256`` signing algorithm used by the Vehicle
Command HTTP Proxy to sign fleet telemetry configurations.  This lets
tescmd call the ``fleet_telemetry_config_jws`` endpoint directly,
without requiring the Go-based ``tesla-http-proxy`` binary.

Algorithm reference: github.com/teslamotors/vehicle-command
    internal/schnorr/sign.go   — Sign()
    internal/schnorr/schnorr.go — challenge(), Verify()
    internal/authentication/jwt.go — SignMessage()
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import struct
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# ---------------------------------------------------------------------------
# P-256 curve constants
# ---------------------------------------------------------------------------

P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551

_P256_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_P256_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5

# Generator point G in uncompressed X9.62 form (04 || X || Y).
P256_GENERATOR_BYTES = b"\x04" + _P256_GX.to_bytes(32, "big") + _P256_GY.to_bytes(32, "big")

_SCALAR_LEN = 32


# ---------------------------------------------------------------------------
# Low-level Schnorr primitives
# ---------------------------------------------------------------------------


def _deterministic_nonce(scalar: bytes, message_hash: bytes) -> bytes:
    """RFC 6979 deterministic nonce generation for P-256 / SHA-256.

    Mirrors ``DeterministicNonce`` in the Go SDK's ``internal/schnorr/sign.go``.
    """
    # Reduce message hash mod n
    h1_int = int.from_bytes(message_hash, "big") % P256_ORDER
    h1 = h1_int.to_bytes(32, "big")

    # HMAC-DRBG initialisation (RFC 6979 S3.2 steps a-d)
    k_mac = b"\x00" * 32
    v = b"\x01" * 32

    # Step d
    k_mac = hmac.new(k_mac, v + b"\x00" + scalar + h1, hashlib.sha256).digest()
    # Step e
    v = hmac.new(k_mac, v, hashlib.sha256).digest()
    # Step f
    k_mac = hmac.new(k_mac, v + b"\x01" + scalar + h1, hashlib.sha256).digest()
    # Step g
    v = hmac.new(k_mac, v, hashlib.sha256).digest()

    # Step h — generate candidates
    while True:
        v = hmac.new(k_mac, v, hashlib.sha256).digest()
        nonce_int = int.from_bytes(v, "big")
        if 0 < nonce_int < P256_ORDER:
            return v

        # Retry per spec
        k_mac = hmac.new(k_mac, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k_mac, v, hashlib.sha256).digest()


def _write_length_value(h: Any, data: bytes) -> None:
    """Write a 4-byte big-endian length prefix then the data into *h*."""
    h.update(struct.pack(">I", len(data)))
    h.update(data)


def _challenge(
    public_nonce_uncompressed: bytes,
    sender_public_uncompressed: bytes,
    message: bytes,
) -> bytes:
    """Compute the Schnorr challenge hash.

    ``SHA-256(len(G) || G || len(R) || R || len(P) || P || len(m) || m)``

    Mirrors ``challenge()`` in ``internal/schnorr/schnorr.go``.
    """
    h = hashlib.sha256()
    _write_length_value(h, P256_GENERATOR_BYTES)
    _write_length_value(h, public_nonce_uncompressed)
    _write_length_value(h, sender_public_uncompressed)
    _write_length_value(h, message)
    return h.digest()


def schnorr_sign(
    private_key: ec.EllipticCurvePrivateKey,
    message: bytes,
) -> bytes:
    """Produce a 96-byte Tesla Schnorr/P-256 signature.

    Returns ``nonce_X (32) || nonce_Y (32) || r (32)``.
    """
    # Private scalar bytes (big-endian, zero-padded to 32 bytes)
    priv_numbers = private_key.private_numbers()
    scalar = priv_numbers.private_value.to_bytes(_SCALAR_LEN, "big")

    # Public key (uncompressed X9.62)
    sender_public = private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )

    # 1. Deterministic nonce
    digest = hashlib.sha256(message).digest()
    nonce_bytes = _deterministic_nonce(scalar, digest)
    nonce_int = int.from_bytes(nonce_bytes, "big")

    # 2. Nonce public key  (k·G)
    nonce_key = ec.derive_private_key(nonce_int, ec.SECP256R1())
    nonce_public = nonce_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )  # 65 bytes: 04 || X || Y

    # 3. Challenge  c = H(G, R, P, m)
    c_bytes = _challenge(nonce_public, sender_public, message)
    c_int = int.from_bytes(c_bytes, "big")

    # 4. Response  r = k - x*c  (mod n)
    x_int = priv_numbers.private_value
    r_int = (nonce_int - x_int * c_int) % P256_ORDER

    # 5. Signature = nonce_X || nonce_Y || r  (strip 0x04 prefix)
    sig = nonce_public[1:] + r_int.to_bytes(_SCALAR_LEN, "big")
    assert len(sig) == 3 * _SCALAR_LEN
    return sig


# ---------------------------------------------------------------------------
# JWS token construction  (Tesla.SS256)
# ---------------------------------------------------------------------------

_JWS_HEADER = {"alg": "Tesla.SS256", "typ": "JWT"}


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding (per RFC 7515)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_fleet_telemetry_config(
    private_key: ec.EllipticCurvePrivateKey,
    config: dict[str, Any],
) -> str:
    """Create a JWS token for a fleet telemetry config payload.

    The *config* dict (hostname, ca, fields, alert_types) is signed with the
    Tesla.SS256 algorithm.  ``iss`` and ``aud`` claims are set automatically.

    Returns the compact JWS string for the ``fleet_telemetry_config_jws``
    endpoint's ``token`` field.
    """
    # Build claims — shallow copy so we don't mutate the caller's dict
    claims: dict[str, Any] = dict(config)

    # iss = base64(uncompressed public key bytes)
    pub_bytes = private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    claims["iss"] = base64.standard_b64encode(pub_bytes).decode("ascii")
    claims["aud"] = "com.tesla.fleet.TelemetryClient"

    # Serialise header & payload
    header_b64 = _b64url(json.dumps(_JWS_HEADER, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(claims, separators=(",", ":")).encode())

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    # Sign
    sig = schnorr_sign(private_key, signing_input)
    sig_b64 = _b64url(sig)

    return f"{header_b64}.{payload_b64}.{sig_b64}"
