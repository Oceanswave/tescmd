"""Tests for EC key generation and loading."""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec

from tescmd.crypto.keys import (
    generate_ec_key_pair,
    get_key_fingerprint,
    get_public_key_path,
    has_key_pair,
    load_private_key,
    load_public_key_pem,
)


class TestGenerateEcKeyPair:
    def test_creates_key_files(self, tmp_path: Path) -> None:
        priv, pub = generate_ec_key_pair(tmp_path)
        assert priv.exists()
        assert pub.exists()
        assert priv.name == "private_key.pem"
        assert pub.name == "public_key.pem"

    def test_private_key_permissions(self, tmp_path: Path) -> None:
        priv, _pub = generate_ec_key_pair(tmp_path)
        mode = priv.stat().st_mode
        assert mode & stat.S_IRUSR  # owner can read
        assert mode & stat.S_IWUSR  # owner can write
        assert not (mode & stat.S_IRGRP)  # group cannot read
        assert not (mode & stat.S_IROTH)  # others cannot read

    def test_refuses_overwrite_by_default(self, tmp_path: Path) -> None:
        generate_ec_key_pair(tmp_path)
        with pytest.raises(FileExistsError):
            generate_ec_key_pair(tmp_path)

    def test_overwrite_flag(self, tmp_path: Path) -> None:
        priv1, _ = generate_ec_key_pair(tmp_path)
        content1 = priv1.read_bytes()
        priv2, _ = generate_ec_key_pair(tmp_path, overwrite=True)
        content2 = priv2.read_bytes()
        assert content1 != content2  # new key generated

    def test_creates_intermediate_directories(self, tmp_path: Path) -> None:
        key_dir = tmp_path / "deep" / "nested" / "keys"
        priv, pub = generate_ec_key_pair(key_dir)
        assert priv.exists()
        assert pub.exists()

    def test_pem_format(self, tmp_path: Path) -> None:
        priv, pub = generate_ec_key_pair(tmp_path)
        priv_text = priv.read_text()
        pub_text = pub.read_text()
        assert priv_text.startswith("-----BEGIN PRIVATE KEY-----")
        assert pub_text.startswith("-----BEGIN PUBLIC KEY-----")


class TestLoadPrivateKey:
    def test_loads_valid_key(self, tmp_path: Path) -> None:
        generate_ec_key_pair(tmp_path)
        key = load_private_key(tmp_path)
        assert isinstance(key, ec.EllipticCurvePrivateKey)

    def test_raises_on_missing_key(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_private_key(tmp_path)


class TestLoadPublicKeyPem:
    def test_loads_pem_string(self, tmp_path: Path) -> None:
        generate_ec_key_pair(tmp_path)
        pem = load_public_key_pem(tmp_path)
        assert isinstance(pem, str)
        assert "BEGIN PUBLIC KEY" in pem

    def test_raises_on_missing_key(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_public_key_pem(tmp_path)


class TestGetPublicKeyPath:
    def test_returns_path(self, tmp_path: Path) -> None:
        path = get_public_key_path(tmp_path)
        assert path == tmp_path / "public_key.pem"


class TestHasKeyPair:
    def test_false_when_empty(self, tmp_path: Path) -> None:
        assert has_key_pair(tmp_path) is False

    def test_true_after_generation(self, tmp_path: Path) -> None:
        generate_ec_key_pair(tmp_path)
        assert has_key_pair(tmp_path) is True

    def test_false_with_only_private(self, tmp_path: Path) -> None:
        generate_ec_key_pair(tmp_path)
        (tmp_path / "public_key.pem").unlink()
        assert has_key_pair(tmp_path) is False


class TestGetKeyFingerprint:
    def test_returns_hex_string(self, tmp_path: Path) -> None:
        generate_ec_key_pair(tmp_path)
        fp = get_key_fingerprint(tmp_path)
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA-256 hex = 64 chars
        int(fp, 16)  # valid hex

    def test_deterministic(self, tmp_path: Path) -> None:
        generate_ec_key_pair(tmp_path)
        fp1 = get_key_fingerprint(tmp_path)
        fp2 = get_key_fingerprint(tmp_path)
        assert fp1 == fp2

    def test_different_keys_different_fingerprints(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "a"
        dir2 = tmp_path / "b"
        generate_ec_key_pair(dir1)
        generate_ec_key_pair(dir2)
        assert get_key_fingerprint(dir1) != get_key_fingerprint(dir2)

    def test_raises_on_missing_key(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_key_fingerprint(tmp_path)
