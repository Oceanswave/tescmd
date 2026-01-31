"""Shared fixtures for telemetry tests."""

from __future__ import annotations

import pytest


@pytest.fixture()
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> dict[str, str]:
    """Set environment variables for CLI tests without real credentials."""
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
