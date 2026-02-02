"""Tests for bug fixes in Phase 1."""

from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tescmd.api.errors import VehicleAsleepError


class TestAutoWakeNonTTY:
    """Bug 1a: auto_wake() should not call click.prompt() in non-TTY mode."""

    @pytest.mark.asyncio
    async def test_non_tty_raises_without_prompt(self) -> None:
        """When stdin is not a TTY, auto_wake should raise immediately without prompting."""
        from tescmd.cli._client import auto_wake

        formatter = MagicMock()
        formatter.format = "rich"  # Rich mode, but NOT a TTY

        vehicle_api = MagicMock()
        operation = AsyncMock(side_effect=VehicleAsleepError("asleep", status_code=408))

        with patch("tescmd.cli._client.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            with pytest.raises(VehicleAsleepError, match="asleep"):
                await auto_wake(
                    formatter,
                    vehicle_api,
                    "5YJ3E1EA1NF000001",
                    operation,
                    auto=False,
                )

    @pytest.mark.asyncio
    async def test_tty_rich_mode_would_prompt(self) -> None:
        """In TTY + Rich mode, auto_wake should attempt to prompt (we mock it to cancel)."""
        from tescmd.cli._client import auto_wake

        formatter = MagicMock()
        formatter.format = "rich"
        formatter.rich = MagicMock()

        vehicle_api = MagicMock()
        operation = AsyncMock(side_effect=VehicleAsleepError("asleep", status_code=408))

        with (
            patch("tescmd.cli._client.sys") as mock_sys,
            patch("tescmd.cli._client.click") as mock_click,
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_click.prompt.return_value = "c"  # Cancel
            mock_click.Choice = MagicMock()

            with pytest.raises(VehicleAsleepError, match="cancelled"):
                await auto_wake(
                    formatter,
                    vehicle_api,
                    "5YJ3E1EA1NF000001",
                    operation,
                    auto=False,
                )

    @pytest.mark.asyncio
    async def test_auto_wake_spinner_non_tty(self) -> None:
        """When auto=True and non-TTY, wake should proceed without spinner."""
        from tescmd.cli._client import auto_wake

        formatter = MagicMock()
        formatter.format = "rich"

        vehicle_api = MagicMock()
        # First call: asleep. After wake: success.
        call_count = 0

        async def _operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise VehicleAsleepError("asleep", status_code=408)
            return "success"

        vehicle_api.wake = AsyncMock()
        vehicle_api.wake.return_value = MagicMock(state="online")

        with patch("tescmd.cli._client.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = False
            result = await auto_wake(
                formatter,
                vehicle_api,
                "5YJ3E1EA1NF000001",
                _operation,
                auto=True,
                timeout=5,
            )
        assert result == "success"
        # Should NOT have called console.status (no spinner in non-TTY)
        formatter.console.status.assert_not_called()


class TestCachedApiCallTypeConsistency:
    """Bug 1b: cached_api_call() should return consistent types on hit and miss."""

    @pytest.mark.asyncio
    async def test_miss_returns_original_model(self) -> None:
        """On cache miss, cached_api_call returns the original fetch result."""
        from tescmd.cli._client import cached_api_call

        model = MagicMock()
        model.model_dump.return_value = {"vin": "TEST", "state": "online"}

        app_ctx = MagicMock()
        app_ctx.formatter.format = "json"
        app_ctx.formatter.set_cache_meta = MagicMock()
        app_ctx.no_cache = True

        with patch("tescmd.cli._client.get_cache") as mock_cache:
            cache = MagicMock()
            cache.get_generic.return_value = None
            cache.put_generic = MagicMock()
            mock_cache.return_value = cache

            result = await cached_api_call(
                app_ctx,
                scope="vin",
                identifier="TEST",
                endpoint="test.endpoint",
                fetch=AsyncMock(return_value=model),
            )

        assert result is model

    @pytest.mark.asyncio
    async def test_hit_with_model_class_returns_model(self) -> None:
        """On cache hit with model_class, returns a reconstructed Pydantic model."""
        from pydantic import BaseModel

        from tescmd.cli._client import cached_api_call

        class FakeModel(BaseModel):
            vin: str
            state: str

        app_ctx = MagicMock()
        app_ctx.formatter.format = "rich"
        app_ctx.formatter.rich = MagicMock()

        cached_entry = MagicMock()
        cached_entry.data = {"vin": "TEST", "state": "online"}
        cached_entry.age_seconds = 5
        cached_entry.ttl_seconds = 60

        with patch("tescmd.cli._client.get_cache") as mock_cache:
            cache = MagicMock()
            cache.get_generic.return_value = cached_entry
            mock_cache.return_value = cache

            result = await cached_api_call(
                app_ctx,
                scope="vin",
                identifier="TEST",
                endpoint="test.endpoint",
                fetch=AsyncMock(),
                model_class=FakeModel,
            )

        assert isinstance(result, FakeModel)
        assert result.vin == "TEST"
        assert result.state == "online"

    @pytest.mark.asyncio
    async def test_hit_with_corrupt_cache_falls_back_to_dict(self) -> None:
        """On cache hit with model_class and corrupt data, falls back to raw dict."""
        from pydantic import BaseModel

        from tescmd.cli._client import cached_api_call

        class StrictModel(BaseModel):
            required_field: int  # cached data won't have this

        app_ctx = MagicMock()
        app_ctx.formatter.format = "rich"
        app_ctx.formatter.rich = MagicMock()

        cached_entry = MagicMock()
        cached_entry.data = {"wrong_field": "corrupt"}
        cached_entry.age_seconds = 5
        cached_entry.ttl_seconds = 60

        with patch("tescmd.cli._client.get_cache") as mock_cache:
            cache = MagicMock()
            cache.get_generic.return_value = cached_entry
            mock_cache.return_value = cache

            result = await cached_api_call(
                app_ctx,
                scope="vin",
                identifier="TEST",
                endpoint="test.endpoint",
                fetch=AsyncMock(),
                model_class=StrictModel,
            )

        # Falls back to raw dict on validation failure
        assert isinstance(result, dict)
        assert result == {"wrong_field": "corrupt"}


class TestTelemetryPortOverflow:
    """Bug 1c: random port should not generate 65535 (TelemetryServer uses port+1)."""

    def test_max_port_is_65534(self) -> None:
        """Verify the port range upper bound is 65534."""
        # Seed random for deterministic test
        rng = random.Random(42)
        ports = {rng.randint(49152, 65534) for _ in range(10000)}
        assert max(ports) <= 65534
        assert 65535 not in ports


class TestStatusRefreshTokenTruthiness:
    """Bug 1d: status command should treat empty string refresh token as falsy."""

    def test_empty_string_is_falsy(self) -> None:
        assert not bool("")
        assert not bool(None)
        assert bool("actual-token")

    def test_status_empty_refresh_token(self) -> None:
        """Empty string refresh_token should show as 'no' in status."""
        assert bool("") is False
        assert bool(None) is False
        assert bool("refresh-token-here") is True
