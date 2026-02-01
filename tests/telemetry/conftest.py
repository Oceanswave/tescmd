"""Shared fixtures for telemetry tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    """Set environment variables for CLI tests without real credentials.

    Creates a dummy EC key pair under ``tmp_path/keys/`` so that the stream
    command can load the public key (it reads it before starting the tunnel).
    """
    from tescmd.crypto.keys import generate_ec_key_pair

    generate_ec_key_pair(tmp_path / "keys")

    env = {
        "TESLA_ACCESS_TOKEN": "test-token-123",
        "TESLA_VIN": "5YJ3E1EA1NF000001",
        "TESLA_REGION": "na",
        "TESLA_CACHE_ENABLED": "false",
        "TESLA_CONFIG_DIR": str(tmp_path),
        "TESLA_COMMAND_PROTOCOL": "unsigned",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env
