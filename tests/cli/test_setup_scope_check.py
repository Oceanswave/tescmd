"""Tests for OAuth scope checking during setup (H4).

Verifies that _oauth_login_step re-authenticates when existing token
scopes are insufficient for the selected tier.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tescmd.models.auth import DEFAULT_SCOPES


class TestOAuthScopeCheck:
    """Verify setup.py _oauth_login_step checks stored scopes."""

    @pytest.mark.asyncio
    async def test_skips_oauth_when_all_scopes_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When stored scopes match DEFAULT_SCOPES, OAuth should be skipped."""
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/test-config")

        from tescmd.cli.main import AppContext
        from tescmd.cli.setup import _oauth_login_step
        from tescmd.models.config import AppSettings
        from tescmd.output.formatter import OutputFormatter

        formatter = OutputFormatter(force_format="rich")
        app_ctx = AppContext(
            vin=None,
            profile="default",
            output_format="rich",
            quiet=False,
            region="na",
            verbose=False,
        )
        settings = AppSettings()

        mock_store = MagicMock()
        mock_store.has_token = True
        mock_store.metadata = {"scopes": DEFAULT_SCOPES, "region": "na"}

        with (
            patch("tescmd.auth.token_store.TokenStore", return_value=mock_store),
            patch("tescmd.auth.oauth.login_flow", new_callable=AsyncMock) as mock_login,
        ):
            await _oauth_login_step(formatter, app_ctx, settings, "cid", "csec")
            mock_login.assert_not_called()

    @pytest.mark.asyncio
    async def test_reauths_when_missing_command_scopes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When stored scopes lack vehicle_cmds, OAuth should re-run."""
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/test-config")

        from tescmd.cli.main import AppContext
        from tescmd.cli.setup import _oauth_login_step
        from tescmd.models.config import AppSettings
        from tescmd.output.formatter import OutputFormatter

        formatter = OutputFormatter(force_format="rich")
        app_ctx = AppContext(
            vin=None,
            profile="default",
            output_format="rich",
            quiet=False,
            region="na",
            verbose=False,
        )
        settings = AppSettings()

        # Readonly scopes — missing vehicle_cmds and vehicle_charging_cmds
        mock_store = MagicMock()
        mock_store.has_token = True
        mock_store.metadata = {
            "scopes": ["openid", "offline_access", "vehicle_device_data", "user_data"],
            "region": "na",
        }

        with (
            patch("tescmd.auth.token_store.TokenStore", return_value=mock_store),
            patch("tescmd.auth.oauth.login_flow", new_callable=AsyncMock) as mock_login,
        ):
            await _oauth_login_step(formatter, app_ctx, settings, "cid", "csec")
            mock_login.assert_called_once()
            # Verify it requests the full DEFAULT_SCOPES
            call_kwargs = mock_login.call_args
            assert set(call_kwargs.kwargs["scopes"]) == set(DEFAULT_SCOPES)

    @pytest.mark.asyncio
    async def test_reauths_when_no_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no token exists at all, OAuth should run."""
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/test-config")

        from tescmd.cli.main import AppContext
        from tescmd.cli.setup import _oauth_login_step
        from tescmd.models.config import AppSettings
        from tescmd.output.formatter import OutputFormatter

        formatter = OutputFormatter(force_format="rich")
        app_ctx = AppContext(
            vin=None,
            profile="default",
            output_format="rich",
            quiet=False,
            region="na",
            verbose=False,
        )
        settings = AppSettings()

        mock_store = MagicMock()
        mock_store.has_token = False

        with (
            patch("tescmd.auth.token_store.TokenStore", return_value=mock_store),
            patch("tescmd.auth.oauth.login_flow", new_callable=AsyncMock) as mock_login,
        ):
            await _oauth_login_step(formatter, app_ctx, settings, "cid", "csec")
            mock_login.assert_called_once()

    @pytest.mark.asyncio
    async def test_reauths_when_metadata_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When token exists but metadata is None, treat as missing scopes."""
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/test-config")

        from tescmd.cli.main import AppContext
        from tescmd.cli.setup import _oauth_login_step
        from tescmd.models.config import AppSettings
        from tescmd.output.formatter import OutputFormatter

        formatter = OutputFormatter(force_format="rich")
        app_ctx = AppContext(
            vin=None,
            profile="default",
            output_format="rich",
            quiet=False,
            region="na",
            verbose=False,
        )
        settings = AppSettings()

        mock_store = MagicMock()
        mock_store.has_token = True
        mock_store.metadata = None  # No metadata at all

        with (
            patch("tescmd.auth.token_store.TokenStore", return_value=mock_store),
            patch("tescmd.auth.oauth.login_flow", new_callable=AsyncMock) as mock_login,
        ):
            await _oauth_login_step(formatter, app_ctx, settings, "cid", "csec")
            mock_login.assert_called_once()
