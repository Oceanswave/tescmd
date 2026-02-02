"""Tests for CommandDispatcher — OpenClaw inbound request handling."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tescmd.api.errors import AuthError, TierError, VehicleAsleepError
from tescmd.openclaw.dispatcher import CommandDispatcher
from tescmd.openclaw.telemetry_store import TelemetryStore


def _mock_app_ctx() -> MagicMock:
    """Return a minimal mock AppContext."""
    ctx = MagicMock()
    ctx.vin = "VIN123"
    ctx.region = "na"
    ctx.profile = "default"
    ctx.no_cache = True
    ctx.auto_wake = True
    ctx.formatter = MagicMock()
    ctx.formatter.format = "json"
    return ctx


def _store_with(**fields: Any) -> TelemetryStore:
    """Build a TelemetryStore pre-populated with the given field values."""
    store = TelemetryStore()
    ts = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
    for name, value in fields.items():
        store.update(name, value, ts)
    return store


def _make_command_result(reason: str = "ok") -> MagicMock:
    """Build a mock CommandResponse."""
    result = MagicMock()
    result.response.result = True
    result.response.reason = reason
    return result


class TestDispatchRouting:
    @pytest.mark.asyncio
    async def test_unknown_method_returns_none(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        result = await d.dispatch({"method": "unknown.thing", "params": {}})
        assert result is None

    @pytest.mark.asyncio
    async def test_dispatch_routes_to_handler(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(Soc=72.0)
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "battery.get", "params": {}})
        assert result is not None
        assert "battery_level" in result


class TestReadHandlersFromStore:
    """Read handlers should return data from the telemetry store when available."""

    @pytest.mark.asyncio
    async def test_location_get_from_store(self) -> None:
        ctx = _mock_app_ctx()
        loc = {"latitude": 37.77, "longitude": -122.42, "heading": 90, "speed": 30}
        store = _store_with(Location=loc)
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "location.get", "params": {}})
        assert result["latitude"] == 37.77
        assert result["longitude"] == -122.42

    @pytest.mark.asyncio
    async def test_battery_get_from_store(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(Soc=72.0, EstBatteryRange=218.5)
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "battery.get", "params": {}})
        assert result["battery_level"] == 72.0
        assert result["range_miles"] == 218.5

    @pytest.mark.asyncio
    async def test_battery_get_from_battery_level(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(BatteryLevel=65.0)
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "battery.get", "params": {}})
        assert result["battery_level"] == 65.0

    @pytest.mark.asyncio
    async def test_temperature_get_from_store(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(InsideTemp=22.5, OutsideTemp=15.0)
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "temperature.get", "params": {}})
        assert result["inside_temp_c"] == 22.5
        assert result["outside_temp_c"] == 15.0

    @pytest.mark.asyncio
    async def test_speed_get_from_store(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(VehicleSpeed=65.0)
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "speed.get", "params": {}})
        assert result["speed_mph"] == 65.0

    @pytest.mark.asyncio
    async def test_charge_state_get_from_store(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(ChargeState="Charging")
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "charge_state.get", "params": {}})
        assert result["charge_state"] == "Charging"

    @pytest.mark.asyncio
    async def test_security_get_from_store(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(Locked=True, SentryMode=False)
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "security.get", "params": {}})
        assert result["locked"] is True
        assert result["sentry_mode"] is False


class TestReadHandlersColdStart:
    """Read handlers return pending when store and cache are both empty."""

    @pytest.mark.asyncio
    async def test_cold_start_returns_pending(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=TelemetryStore())
        result = await d.dispatch({"method": "battery.get", "params": {}})
        assert result is not None
        assert result.get("pending") is True

    @pytest.mark.asyncio
    async def test_location_cold_start_returns_pending(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=TelemetryStore())
        result = await d.dispatch({"method": "location.get", "params": {}})
        assert result is not None
        assert result.get("pending") is True


class TestReadHandlersFallbackToCache:
    """Read handlers use cached vehicle data when store is empty but API was fetched."""

    @pytest.mark.asyncio
    async def test_battery_get_from_cache(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=TelemetryStore())
        d._vehicle_data_cache = {
            "charge_state": {"battery_level": 80, "battery_range": 250.0},
        }
        result = await d.dispatch({"method": "battery.get", "params": {}})
        assert result is not None
        assert result["battery_level"] == 80
        assert result["range_miles"] == 250.0

    @pytest.mark.asyncio
    async def test_location_get_from_cache(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=TelemetryStore())
        d._vehicle_data_cache = {
            "drive_state": {"latitude": 40.7, "longitude": -74.0, "heading": 180, "speed": 0},
        }
        result = await d.dispatch({"method": "location.get", "params": {}})
        assert result is not None
        assert result["latitude"] == 40.7


class TestWriteHandlers:
    """Write handlers should call the correct cmd_api method."""

    @pytest.mark.asyncio
    async def test_door_lock(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)

        cmd_result = _make_command_result("Doors locked.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_vehicle_api = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.door_lock = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, mock_vehicle_api, mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "door.lock", "params": {}})

        assert result["result"] is True
        assert result["reason"] == "Doors locked."
        mock_cmd_api.door_lock.assert_awaited_once_with("VIN1")

    @pytest.mark.asyncio
    async def test_door_unlock(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result("Doors unlocked.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.door_unlock = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "door.unlock", "params": {}})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_climate_on(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.auto_conditioning_start = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "climate.on", "params": {}})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_climate_set_temp(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.set_temps = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "climate.set_temp", "params": {"temp": 72.0}})
        assert result["result"] is True
        mock_cmd_api.set_temps.assert_awaited_once_with(
            "VIN1", driver_temp=72.0, passenger_temp=72.0
        )

    @pytest.mark.asyncio
    async def test_climate_set_temp_missing_param(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="requires 'temp'"):
            await d.dispatch({"method": "climate.set_temp", "params": {}})

    @pytest.mark.asyncio
    async def test_charge_set_limit(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.set_charge_limit = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "charge.set_limit", "params": {"percent": 80}})
        assert result["result"] is True
        mock_cmd_api.set_charge_limit.assert_awaited_once_with("VIN1", percent=80)

    @pytest.mark.asyncio
    async def test_charge_set_limit_missing_param(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="requires 'percent'"):
            await d.dispatch({"method": "charge.set_limit", "params": {}})

    @pytest.mark.asyncio
    async def test_trunk_open(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.actuate_trunk = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "trunk.open", "params": {}})
        assert result["result"] is True
        mock_cmd_api.actuate_trunk.assert_awaited_once_with("VIN1", which_trunk="rear")

    @pytest.mark.asyncio
    async def test_frunk_open(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.actuate_trunk = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "frunk.open", "params": {}})
        assert result["result"] is True
        mock_cmd_api.actuate_trunk.assert_awaited_once_with("VIN1", which_trunk="front")

    @pytest.mark.asyncio
    async def test_flash_lights(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.flash_lights = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "flash_lights", "params": {}})
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_sentry_on(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.set_sentry_mode = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "sentry.on", "params": {}})
        assert result["result"] is True
        mock_cmd_api.set_sentry_mode.assert_awaited_once_with("VIN1", on=True)


class TestAutoWakeRetry:
    @pytest.mark.asyncio
    async def test_auto_wake_retries_on_asleep(self) -> None:
        """Write handler retries once after VehicleAsleepError."""
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)

        call_count = 0
        cmd_result = _make_command_result("Locked after wake.")

        async def _lock(vin: str) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise VehicleAsleepError("asleep", status_code=408)
            return cmd_result

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = MagicMock()
        mock_cmd_api.door_lock = _lock

        mock_wake_client = AsyncMock()
        mock_wake_client.close = AsyncMock()
        mock_wake_api = AsyncMock()
        mock_wake_api.wake = AsyncMock()

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch(
                "tescmd.openclaw.dispatcher.get_vehicle_api",
                return_value=(mock_wake_client, mock_wake_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
        ):
            result = await d.dispatch({"method": "door.lock", "params": {}})

        assert result["result"] is True
        assert call_count == 2
        mock_wake_api.wake.assert_awaited_once_with("VIN1")


class TestErrorPropagation:
    @pytest.mark.asyncio
    async def test_auth_error_propagates(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)

        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.door_lock = AsyncMock(side_effect=AuthError("unauthorized", status_code=401))

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            pytest.raises(AuthError),
        ):
            await d.dispatch({"method": "door.lock", "params": {}})

    @pytest.mark.asyncio
    async def test_tier_error_propagates(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                side_effect=TierError("readonly tier"),
            ),
            pytest.raises(TierError),
        ):
            await d.dispatch({"method": "door.lock", "params": {}})
