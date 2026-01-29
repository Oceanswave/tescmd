from __future__ import annotations

import os

import pytest

from tescmd.models.config import AppSettings, Profile


class TestProfile:
    def test_defaults(self) -> None:
        p = Profile()
        assert p.region == "na"
        assert p.vin is None
        assert p.output_format is None
        assert p.client_id is None
        assert p.client_secret is None

    def test_with_values(self) -> None:
        p = Profile(
            region="eu",
            vin="5YJ3E1EA1NF000001",
            output_format="json",
            client_id="my-id",
            client_secret="my-secret",
        )
        assert p.region == "eu"
        assert p.vin == "5YJ3E1EA1NF000001"
        assert p.output_format == "json"
        assert p.client_id == "my-id"
        assert p.client_secret == "my-secret"


class TestAppSettings:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clear any TESLA_ env vars that might be set in the environment
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        assert settings.client_id is None
        assert settings.client_secret is None
        assert settings.vin is None
        assert settings.region == "na"
        assert settings.token_file is None
        assert settings.config_dir == "~/.config/tescmd"
        assert settings.output_format is None
        assert settings.profile == "default"
        assert settings.access_token is None
        assert settings.refresh_token is None

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Clear any existing TESLA_ env vars first
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("TESLA_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("TESLA_REGION", "eu")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        assert settings.client_id == "test-client-id"
        assert settings.region == "eu"
        assert settings.vin == "5YJ3E1EA1NF000001"
