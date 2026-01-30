"""EC P-256 key generation and loading for Tesla Fleet API command signing."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DEFAULT_KEY_DIR = "~/.config/tescmd/keys"
PRIVATE_KEY_FILE = "private_key.pem"
PUBLIC_KEY_FILE = "public_key.pem"


def generate_ec_key_pair(
    key_dir: Path | str | None = None,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Generate an EC P-256 key pair and write PEM files.

    Returns the (private_key_path, public_key_path) tuple.
    """
    resolved = _resolve_key_dir(key_dir)
    resolved.mkdir(parents=True, exist_ok=True)

    priv_path = resolved / PRIVATE_KEY_FILE
    pub_path = resolved / PUBLIC_KEY_FILE

    if priv_path.exists() and not overwrite:
        raise FileExistsError(
            f"Key pair already exists at {resolved}. Use overwrite=True to replace."
        )

    private_key = ec.generate_private_key(ec.SECP256R1())

    # Write private key — PEM, no encryption
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    priv_path.write_bytes(priv_pem)
    priv_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    # Write public key — PEM
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    pub_path.write_bytes(pub_pem)

    return (priv_path, pub_path)


def load_private_key(key_dir: Path | str | None = None) -> ec.EllipticCurvePrivateKey:
    """Load the private key from disk."""
    resolved = _resolve_key_dir(key_dir)
    priv_path = resolved / PRIVATE_KEY_FILE

    if not priv_path.exists():
        raise FileNotFoundError(
            f"Private key not found at {priv_path}. Run 'tescmd key generate' first."
        )

    key = serialization.load_pem_private_key(priv_path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise TypeError(f"Expected EC private key, got {type(key).__name__}")
    return key


def load_public_key_pem(key_dir: Path | str | None = None) -> str:
    """Load the public key PEM as a string (for deployment)."""
    resolved = _resolve_key_dir(key_dir)
    pub_path = resolved / PUBLIC_KEY_FILE

    if not pub_path.exists():
        raise FileNotFoundError(
            f"Public key not found at {pub_path}. Run 'tescmd key generate' first."
        )

    return pub_path.read_text()


def get_public_key_path(key_dir: Path | str | None = None) -> Path:
    """Return the resolved path to the public key file."""
    return _resolve_key_dir(key_dir) / PUBLIC_KEY_FILE


def has_key_pair(key_dir: Path | str | None = None) -> bool:
    """Return True if both private and public key files exist."""
    resolved = _resolve_key_dir(key_dir)
    return (resolved / PRIVATE_KEY_FILE).exists() and (resolved / PUBLIC_KEY_FILE).exists()


def get_key_fingerprint(key_dir: Path | str | None = None) -> str:
    """Return the SHA-256 hex fingerprint of the public key (DER-encoded)."""
    resolved = _resolve_key_dir(key_dir)
    pub_path = resolved / PUBLIC_KEY_FILE

    if not pub_path.exists():
        raise FileNotFoundError(
            f"Public key not found at {pub_path}. Run 'tescmd key generate' first."
        )

    key = serialization.load_pem_public_key(pub_path.read_bytes())
    der = key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def _resolve_key_dir(key_dir: Path | str | None) -> Path:
    """Resolve the key directory, expanding ~ and defaulting if None."""
    if key_dir is None:
        return Path(DEFAULT_KEY_DIR).expanduser()
    return Path(key_dir).expanduser()
