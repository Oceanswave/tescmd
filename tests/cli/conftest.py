"""Shared fixtures for CLI execution tests."""

from __future__ import annotations

import pytest


@pytest.fixture()
def cli_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set environment variables so TeslaFleetClient works without real credentials."""
    env = {
        "TESLA_ACCESS_TOKEN": "test-token-123",
        "TESLA_VIN": "5YJ3E1EA1NF000001",
        "TESLA_REGION": "na",
        "TESLA_CACHE_ENABLED": "false",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env
