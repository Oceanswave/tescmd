"""Shared fixtures for CLI execution tests."""

from __future__ import annotations

import pytest


@pytest.fixture()
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> dict[str, str]:
    """Set environment variables so TeslaFleetClient works without real credentials.

    Isolates from the developer's real config by pointing ``TESLA_CONFIG_DIR``
    to a temp directory and forcing ``TESLA_COMMAND_PROTOCOL=unsigned`` so that
    existing command tests don't require a signed-channel mock.
    """
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
