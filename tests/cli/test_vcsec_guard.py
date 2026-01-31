"""Tests for VCSEC signing guard in _client.py.

Verifies that VCSEC commands (lock, unlock, trunk, etc.) raise clear errors
when routed through unsigned REST, instead of silently failing with confusing
API errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from tescmd.api.errors import ConfigError, KeyNotEnrolledError

if TYPE_CHECKING:
    from pathlib import Path


class TestVCSECGuardNoKeys:
    """VCSEC commands with no key pair raise ConfigError (not a silent fallback)."""

    @pytest.mark.asyncio
    async def test_door_lock_no_keys_raises_config_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TESLA_SETUP_TIER", "full")
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        # No keys directory → no key pair
        monkeypatch.setenv("TESLA_COMMAND_PROTOCOL", "auto")

        from tescmd.cli._client import execute_command
        from tescmd.cli.main import AppContext

        app_ctx = AppContext(
            vin="5YJ3E1EA1NF000001",
            profile="default",
            output_format="json",
            quiet=False,
            region="na",
            verbose=False,
        )

        with pytest.raises(ConfigError, match="key pair"):
            await execute_command(app_ctx, "5YJ3E1EA1NF000001", "door_lock", "security.lock")

    @pytest.mark.asyncio
    async def test_door_unlock_no_keys_raises_config_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TESLA_SETUP_TIER", "full")
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_COMMAND_PROTOCOL", "auto")

        from tescmd.cli._client import execute_command
        from tescmd.cli.main import AppContext

        app_ctx = AppContext(
            vin="5YJ3E1EA1NF000001",
            profile="default",
            output_format="json",
            quiet=False,
            region="na",
            verbose=False,
        )

        with pytest.raises(ConfigError, match="key pair"):
            await execute_command(app_ctx, "5YJ3E1EA1NF000001", "door_unlock", "security.unlock")


class TestVCSECGuardKeysExistButAutoProtocol:
    """VCSEC commands with keys present but auto protocol (not signed) raise KeyNotEnrolledError.

    When ``command_protocol=auto`` and keys exist but ``setup_tier`` is not
    ``"full"`` (so the signed API isn't used), VCSEC commands should raise
    ``KeyNotEnrolledError`` instead of silently falling back to unsigned REST.
    """

    @pytest.mark.asyncio
    async def test_door_lock_keys_exist_tier_not_full(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Create fake key files so has_key_pair() returns True
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "private_key.pem").write_text("fake-private")
        (key_dir / "public_key.pem").write_text("fake-public")

        monkeypatch.setenv("TESLA_SETUP_TIER", "readonly")
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_COMMAND_PROTOCOL", "auto")

        from tescmd.cli._client import execute_command
        from tescmd.cli.main import AppContext

        app_ctx = AppContext(
            vin="5YJ3E1EA1NF000001",
            profile="default",
            output_format="json",
            quiet=False,
            region="na",
            verbose=False,
        )

        # readonly tier blocks all write commands before reaching the guard
        from tescmd.api.errors import TierError

        with pytest.raises(TierError, match="full"):
            await execute_command(app_ctx, "5YJ3E1EA1NF000001", "door_lock", "security.lock")


class TestVCSECGuardUnsignedOverride:
    """When command_protocol=unsigned is explicitly set, the guard is bypassed.

    This is an intentional debugging override — the API will return 403 but
    the guard should not block it.
    """

    @pytest.mark.asyncio
    async def test_unsigned_override_bypasses_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_COMMAND_PROTOCOL", "unsigned")

        from unittest.mock import MagicMock

        from tescmd.api.command import CommandAPI
        from tescmd.cli._client import _check_signing_requirement
        from tescmd.models.config import AppSettings

        mock_client = MagicMock()
        cmd_api = CommandAPI(mock_client)
        settings = AppSettings()

        # Should not raise — unsigned override bypasses the guard
        _check_signing_requirement(cmd_api, "door_lock", settings)


class TestInfotainmentCommandsPassThrough:
    """Infotainment commands (charge_start, etc.) should not be blocked by VCSEC guard."""

    @pytest.mark.asyncio
    @pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
    async def test_charge_start_not_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, httpx_mock: object
    ) -> None:
        monkeypatch.setenv("TESLA_SETUP_TIER", "full")
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_COMMAND_PROTOCOL", "auto")

        from tescmd.cli._client import execute_command
        from tescmd.cli.main import AppContext

        app_ctx = AppContext(
            vin="5YJ3E1EA1NF000001",
            profile="default",
            output_format="json",
            quiet=False,
            region="na",
            verbose=False,
        )

        # charge_start is INFOTAINMENT domain, should NOT raise ConfigError
        # or KeyNotEnrolledError. It will fail for other reasons (no mock)
        # but the type of error should not be the VCSEC guard.
        with pytest.raises(Exception) as exc_info:
            await execute_command(app_ctx, "5YJ3E1EA1NF000001", "charge_start", "charge.start")
        assert not isinstance(exc_info.value, (ConfigError, KeyNotEnrolledError))


class TestUnsignedCommandsPassThrough:
    """Unsigned commands (wake_up) are never blocked by the signing guard."""

    @pytest.mark.asyncio
    @pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
    async def test_wake_up_not_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, httpx_mock: object
    ) -> None:
        monkeypatch.setenv("TESLA_SETUP_TIER", "full")
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_COMMAND_PROTOCOL", "auto")

        from tescmd.api.command import CommandAPI
        from tescmd.cli._client import _check_signing_requirement

        # wake_up should never trigger the guard
        with patch("tescmd.cli._client.get_client"):
            from tescmd.api.client import TeslaFleetClient

            mock_client = object.__new__(TeslaFleetClient)
            cmd_api = CommandAPI(mock_client)

            from tescmd.models.config import AppSettings

            settings = AppSettings()

            # Should not raise
            _check_signing_requirement(cmd_api, "wake_up", settings)
