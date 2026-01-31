"""Tests for tier enforcement in execute_command."""

from __future__ import annotations

import json

import pytest

from tescmd.api.errors import ConfigError, TierError
from tescmd.cli.main import _handle_known_error
from tescmd.output.formatter import OutputFormatter


class TestTierErrorModel:
    """Verify TierError is a ConfigError subclass."""

    def test_tier_error_is_config_error(self) -> None:
        exc = TierError("test")
        assert isinstance(exc, ConfigError)

    def test_tier_error_message(self) -> None:
        exc = TierError("custom message")
        assert str(exc) == "custom message"


class TestHandleKnownErrorTier:
    """Verify _handle_known_error recognises TierError."""

    def test_handles_tier_error(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            TierError("readonly"),
            None,
            formatter,
            "charge.start",
        )
        assert handled is True

    def test_tier_error_json_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        formatter = OutputFormatter(force_format="json")
        _handle_known_error(
            TierError("This command requires 'full' tier setup. Run 'tescmd setup' to upgrade."),
            None,
            formatter,
            "charge.start",
        )
        captured = capsys.readouterr()
        output = json.loads(captured.err)
        assert output["ok"] is False
        assert output["error"]["code"] == "tier_readonly"
        assert "tescmd setup" in output["error"]["message"]

    def test_tier_error_not_confused_with_other_errors(self) -> None:
        formatter = OutputFormatter(force_format="json")
        handled = _handle_known_error(
            RuntimeError("not a tier error"),
            None,
            formatter,
            "charge.start",
        )
        assert handled is False


class TestReadonlyBlocksExecuteCommand:
    """Verify execute_command raises TierError when tier is readonly."""

    @pytest.mark.asyncio
    async def test_readonly_raises_tier_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_SETUP_TIER", "readonly")
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")

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

        with pytest.raises(TierError) as exc_info:
            await execute_command(app_ctx, "5YJ3E1EA1NF000001", "charge_start", "charge.start")
        assert "tescmd setup" in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
    async def test_full_does_not_raise_tier_error(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: object
    ) -> None:
        monkeypatch.setenv("TESLA_SETUP_TIER", "full")
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")

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

        # The command will fail for API reasons (no mock), but it should
        # NOT raise TierError — that's what we're testing.
        with pytest.raises(Exception) as exc_info:
            await execute_command(app_ctx, "5YJ3E1EA1NF000001", "charge_start", "charge.start")
        assert not isinstance(exc_info.value, TierError)

    @pytest.mark.asyncio
    @pytest.mark.httpx_mock(assert_all_requests_were_expected=False)
    async def test_no_tier_does_not_block(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: object
    ) -> None:
        monkeypatch.delenv("TESLA_SETUP_TIER", raising=False)
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_VIN", "5YJ3E1EA1NF000001")
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "false")

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

        # Should NOT raise TierError — backward compat
        with pytest.raises(Exception) as exc_info:
            await execute_command(app_ctx, "5YJ3E1EA1NF000001", "charge_start", "charge.start")
        assert not isinstance(exc_info.value, TierError)
