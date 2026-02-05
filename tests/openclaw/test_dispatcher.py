"""Tests for CommandDispatcher — OpenClaw inbound request handling."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tescmd.api.errors import (
    AuthError,
    ConfigError,
    KeyNotEnrolledError,
    TierError,
    VehicleAsleepError,
)
from tescmd.openclaw.dispatcher import _METHOD_ALIASES, CommandDispatcher
from tescmd.openclaw.telemetry_store import TelemetryStore
from tescmd.triggers.manager import TriggerManager


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


class TestTelemetryGetHandler:
    """Tests for the generic telemetry.get read handler."""

    @pytest.mark.asyncio
    async def test_telemetry_get_from_store(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(PackVoltage=398.2)
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "telemetry.get", "params": {"field": "PackVoltage"}})
        assert result["field"] == "PackVoltage"
        assert result["value"] == 398.2

    @pytest.mark.asyncio
    async def test_telemetry_get_pending(self) -> None:
        ctx = _mock_app_ctx()
        store = TelemetryStore()
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch({"method": "telemetry.get", "params": {"field": "PackVoltage"}})
        assert result["field"] == "PackVoltage"
        assert result["pending"] is True

    @pytest.mark.asyncio
    async def test_telemetry_get_missing_field_raises(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=TelemetryStore())
        with pytest.raises(ValueError, match="requires 'field'"):
            await d.dispatch({"method": "telemetry.get", "params": {}})

    @pytest.mark.asyncio
    async def test_telemetry_get_no_store_returns_pending(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="V", app_ctx=ctx, telemetry_store=None)
        result = await d.dispatch({"method": "telemetry.get", "params": {"field": "PackVoltage"}})
        assert result["field"] == "PackVoltage"
        assert result["pending"] is True


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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
    async def test_climate_defrost(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.set_preconditioning_max = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch({"method": "climate.defrost", "params": {"on": True}})
        assert result["result"] is True
        mock_cmd_api.set_preconditioning_max.assert_awaited_once_with(
            "VIN1", on=True, manual_override=True
        )

    @pytest.mark.asyncio
    async def test_climate_defrost_off(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.set_preconditioning_max = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch({"method": "climate.defrost", "params": {"on": False}})
        assert result["result"] is True
        mock_cmd_api.set_preconditioning_max.assert_awaited_once_with(
            "VIN1", on=False, manual_override=True
        )

    @pytest.mark.asyncio
    async def test_climate_defrost_defaults_on(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.set_preconditioning_max = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            # No 'on' param — defaults to True
            result = await d.dispatch({"method": "climate.defrost", "params": {}})
        assert result["result"] is True
        mock_cmd_api.set_preconditioning_max.assert_awaited_once_with(
            "VIN1", on=True, manual_override=True
        )

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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch({"method": "sentry.on", "params": {}})
        assert result["result"] is True
        mock_cmd_api.set_sentry_mode.assert_awaited_once_with("VIN1", on=True)


class TestNavHandlers:
    """Tests for navigation command handlers."""

    @pytest.mark.asyncio
    async def test_nav_send(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result("Destination sent.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.share = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch({"method": "nav.send", "params": {"address": "123 Main St"}})
        assert result["result"] is True
        mock_cmd_api.share.assert_awaited_once_with("VIN1", address="123 Main St")

    @pytest.mark.asyncio
    async def test_nav_send_missing_address_raises(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="requires 'address'"):
            await d.dispatch({"method": "nav.send", "params": {}})

    @pytest.mark.asyncio
    async def test_nav_gps(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result("GPS sent.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.navigation_gps_request = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch(
                {"method": "nav.gps", "params": {"lat": 37.77, "lon": -122.42}}
            )
        assert result["result"] is True
        mock_cmd_api.navigation_gps_request.assert_awaited_once_with(
            "VIN1", lat=37.77, lon=-122.42
        )

    @pytest.mark.asyncio
    async def test_nav_gps_with_order(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.navigation_gps_request = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch(
                {"method": "nav.gps", "params": {"lat": 37.77, "lon": -122.42, "order": 2}}
            )
        assert result["result"] is True
        mock_cmd_api.navigation_gps_request.assert_awaited_once_with(
            "VIN1", lat=37.77, lon=-122.42, order=2
        )

    @pytest.mark.asyncio
    async def test_nav_gps_missing_coords_raises(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="requires 'lat' and 'lon'"):
            await d.dispatch({"method": "nav.gps", "params": {"lat": 37.77}})

    @pytest.mark.asyncio
    async def test_nav_supercharger(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result("Navigating to Supercharger.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.navigation_sc_request = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch({"method": "nav.supercharger", "params": {}})
        assert result["result"] is True
        mock_cmd_api.navigation_sc_request.assert_awaited_once_with("VIN1")

    @pytest.mark.asyncio
    async def test_nav_waypoints(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result("Waypoints sent.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.navigation_waypoints_request = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch(
                {
                    "method": "nav.waypoints",
                    "params": {"waypoints": "refId:ChIJ1,refId:ChIJ2"},
                }
            )
        assert result["result"] is True
        mock_cmd_api.navigation_waypoints_request.assert_awaited_once_with(
            "VIN1", waypoints="refId:ChIJ1,refId:ChIJ2"
        )

    @pytest.mark.asyncio
    async def test_nav_waypoints_missing_param_raises(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="requires 'waypoints'"):
            await d.dispatch({"method": "nav.waypoints", "params": {}})

    @pytest.mark.asyncio
    async def test_homelink_trigger(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result("HomeLink triggered.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.trigger_homelink = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch(
                {"method": "homelink.trigger", "params": {"lat": 37.77, "lon": -122.42}}
            )
        assert result["result"] is True
        mock_cmd_api.trigger_homelink.assert_awaited_once_with("VIN1", lat=37.77, lon=-122.42)

    @pytest.mark.asyncio
    async def test_homelink_missing_coords_raises(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="requires 'lat' and 'lon'"):
            await d.dispatch({"method": "homelink.trigger", "params": {"lat": 37.77}})


class TestNavMethodAliases:
    """Tests that nav method aliases resolve correctly via system.run."""

    def test_nav_aliases_present(self) -> None:
        assert "share" in _METHOD_ALIASES
        assert _METHOD_ALIASES["share"] == "nav.send"
        assert "navigation_gps_request" in _METHOD_ALIASES
        assert _METHOD_ALIASES["navigation_gps_request"] == "nav.gps"
        assert "navigation_sc_request" in _METHOD_ALIASES
        assert _METHOD_ALIASES["navigation_sc_request"] == "nav.supercharger"
        assert "navigation_waypoints_request" in _METHOD_ALIASES
        assert _METHOD_ALIASES["navigation_waypoints_request"] == "nav.waypoints"
        assert "trigger_homelink" in _METHOD_ALIASES
        assert _METHOD_ALIASES["trigger_homelink"] == "homelink.trigger"


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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
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


class TestCommandGuards:
    """Tests for check_command_guards() integration in _execute_command."""

    @pytest.mark.asyncio
    async def test_readonly_tier_raises_tier_error(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch(
                "tescmd.openclaw.dispatcher.check_command_guards",
                side_effect=TierError("readonly"),
            ),
            pytest.raises(TierError),
        ):
            await d.dispatch({"method": "door.lock", "params": {}})

    @pytest.mark.asyncio
    async def test_signing_guard_raises_config_error(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch(
                "tescmd.openclaw.dispatcher.check_command_guards",
                side_effect=ConfigError("No EC key pair"),
            ),
            pytest.raises(ConfigError),
        ):
            await d.dispatch({"method": "door.lock", "params": {}})

    @pytest.mark.asyncio
    async def test_key_not_enrolled_raises(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch(
                "tescmd.openclaw.dispatcher.check_command_guards",
                side_effect=KeyNotEnrolledError("not enrolled", status_code=422),
            ),
            pytest.raises(KeyNotEnrolledError),
        ):
            await d.dispatch({"method": "door.unlock", "params": {}})


class TestSystemRun:
    """Tests for system.run meta-dispatch handler."""

    @pytest.mark.asyncio
    async def test_system_run_dispatches_openclaw_method(self) -> None:
        ctx = _mock_app_ctx()
        store = _store_with(Soc=72.0)
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch(
            {"method": "system.run", "params": {"method": "battery.get", "params": {}}}
        )
        assert result is not None
        assert "battery_level" in result

    @pytest.mark.asyncio
    async def test_system_run_resolves_api_style_alias(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        cmd_result = _make_command_result("Locked.")
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_cmd_api = AsyncMock()
        mock_cmd_api.door_lock = AsyncMock(return_value=cmd_result)

        with (
            patch(
                "tescmd.openclaw.dispatcher.get_command_api",
                return_value=(mock_client, AsyncMock(), mock_cmd_api),
            ),
            patch("tescmd.openclaw.dispatcher.invalidate_cache_for_vin"),
            patch("tescmd.openclaw.dispatcher.check_command_guards"),
        ):
            result = await d.dispatch(
                {"method": "system.run", "params": {"method": "door_lock", "params": {}}}
            )
        assert result is not None
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_system_run_unknown_method_returns_none(self) -> None:
        """Unknown inner methods return None (no traceback) for clean gateway handling."""
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        result = await d.dispatch(
            {"method": "system.run", "params": {"method": "nonexistent.cmd", "params": {}}}
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_system_run_self_dispatch_rejected(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="cannot invoke itself"):
            await d.dispatch(
                {"method": "system.run", "params": {"method": "system.run", "params": {}}}
            )

    @pytest.mark.asyncio
    async def test_system_run_missing_method_raises(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(ValueError, match="requires 'method'"):
            await d.dispatch({"method": "system.run", "params": {}})

    @pytest.mark.asyncio
    async def test_system_run_accepts_command_key(self) -> None:
        """system.run accepts 'command' as alias for 'method' (matches gateway protocol)."""
        ctx = _mock_app_ctx()
        store = _store_with(Soc=72.0)
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch(
            {"method": "system.run", "params": {"command": "battery.get", "params": {}}}
        )
        assert result is not None
        assert "battery_level" in result

    @pytest.mark.asyncio
    async def test_system_run_accepts_list_method(self) -> None:
        """system.run normalizes a list value like ['battery.get'] to a string."""
        ctx = _mock_app_ctx()
        store = _store_with(Soc=72.0)
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, telemetry_store=store)
        result = await d.dispatch(
            {"method": "system.run", "params": {"method": ["battery.get"], "params": {}}}
        )
        assert result is not None
        assert "battery_level" in result

    def test_method_aliases_cover_key_commands(self) -> None:
        assert "door_lock" in _METHOD_ALIASES
        assert "door_unlock" in _METHOD_ALIASES
        assert "auto_conditioning_start" in _METHOD_ALIASES
        assert "charge_start" in _METHOD_ALIASES
        assert _METHOD_ALIASES["door_lock"] == "door.lock"


class TestTriggerHandlers:
    """Tests for trigger.* command handlers."""

    @pytest.mark.asyncio
    async def test_trigger_create_via_alias(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch(
            {
                "method": "battery.trigger",
                "params": {"operator": "lt", "value": 20},
            }
        )
        assert result is not None
        assert "id" in result
        assert result["field"] == "BatteryLevel"
        assert result["operator"] == "lt"
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_trigger_create_once(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        await d.dispatch(
            {
                "method": "battery.trigger",
                "params": {"operator": "lt", "value": 10, "once": True},
            }
        )
        trigger = mgr.list_all()[0]
        assert trigger.once is True

    @pytest.mark.asyncio
    async def test_trigger_create_custom_cooldown(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        await d.dispatch(
            {
                "method": "battery.trigger",
                "params": {"operator": "lt", "value": 10, "cooldown_seconds": 30.0},
            }
        )
        trigger = mgr.list_all()[0]
        assert trigger.cooldown_seconds == 30.0

    @pytest.mark.asyncio
    async def test_trigger_create_missing_operator_raises(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        with pytest.raises(ValueError, match="requires 'operator'"):
            await d.dispatch(
                {
                    "method": "battery.trigger",
                    "params": {"value": 20},
                }
            )

    @pytest.mark.asyncio
    async def test_generic_trigger_create_routes(self) -> None:
        """trigger.create routes to the generic create handler."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch(
            {
                "method": "trigger.create",
                "params": {"field": "BatteryLevel", "operator": "lt", "value": 20},
            }
        )
        assert result is not None
        assert result["field"] == "BatteryLevel"
        assert result["operator"] == "lt"
        assert "id" in result
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_trigger_delete_via_domain(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        create_result = await d.dispatch(
            {
                "method": "battery.trigger",
                "params": {"operator": "lt", "value": 20},
            }
        )
        trigger_id = create_result["id"]
        delete_result = await d.dispatch(
            {
                "method": "battery.trigger.delete",
                "params": {"id": trigger_id},
            }
        )
        assert delete_result["deleted"] is True
        assert delete_result["id"] == trigger_id
        assert len(mgr.list_all()) == 0

    @pytest.mark.asyncio
    async def test_trigger_delete_nonexistent(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch(
            {
                "method": "battery.trigger.delete",
                "params": {"id": "nonexistent123"},
            }
        )
        assert result["deleted"] is False

    @pytest.mark.asyncio
    async def test_trigger_delete_missing_id_raises(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        with pytest.raises(ValueError, match="requires 'id'"):
            await d.dispatch({"method": "battery.trigger.delete", "params": {}})

    @pytest.mark.asyncio
    async def test_generic_trigger_delete_routes(self) -> None:
        """trigger.delete is routable as a domain-agnostic delete."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)

        create_result = await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20}}
        )
        trigger_id = create_result["id"]

        result = await d.dispatch(
            {"method": "trigger.delete", "params": {"id": trigger_id}}
        )
        assert result["deleted"] is True
        assert len(mgr.list_all()) == 0

    @pytest.mark.asyncio
    async def test_generic_trigger_list_all(self) -> None:
        """trigger.list returns ALL triggers across all fields."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20}}
        )
        await d.dispatch(
            {"method": "cabin_temp.trigger", "params": {"operator": "gt", "value": 95}}
        )
        result = await d.dispatch({"method": "trigger.list", "params": {}})
        assert result is not None
        assert len(result["triggers"]) == 2
        fields = {t["field"] for t in result["triggers"]}
        assert fields == {"BatteryLevel", "InsideTemp"}

    @pytest.mark.asyncio
    async def test_domain_list_empty(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch({"method": "battery.trigger.list", "params": {}})
        assert result["triggers"] == []

    @pytest.mark.asyncio
    async def test_domain_list_filters_by_field(self) -> None:
        """Each domain list only shows triggers for its own field."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        await d.dispatch(
            {
                "method": "battery.trigger",
                "params": {"operator": "lt", "value": 20},
            }
        )
        await d.dispatch(
            {
                "method": "cabin_temp.trigger",
                "params": {"operator": "gt", "value": 95},  # 95°F → 35°C
            }
        )
        # battery.trigger.list shows only BatteryLevel triggers
        bat = await d.dispatch({"method": "battery.trigger.list", "params": {}})
        assert len(bat["triggers"]) == 1
        assert bat["triggers"][0]["field"] == "BatteryLevel"
        # cabin_temp.trigger.list shows only InsideTemp triggers
        temp = await d.dispatch({"method": "cabin_temp.trigger.list", "params": {}})
        assert len(temp["triggers"]) == 1
        assert temp["triggers"][0]["field"] == "InsideTemp"

    @pytest.mark.asyncio
    async def test_temp_list_includes_fahrenheit(self) -> None:
        """Temperature trigger list includes value_f for display."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        await d.dispatch(
            {
                "method": "cabin_temp.trigger",
                "params": {"operator": "gt", "value": 80},  # 80°F → 26.7°C
            }
        )
        result = await d.dispatch({"method": "cabin_temp.trigger.list", "params": {}})
        t = result["triggers"][0]
        assert t["value"] == 26.7  # stored in Celsius
        assert t["value_f"] == 80.1  # converted back to Fahrenheit

    @pytest.mark.asyncio
    async def test_trigger_poll_returns_unknown_command(self) -> None:
        """trigger.poll is no longer a recognized command."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch({"method": "trigger.poll", "params": {}})
        assert result is None


class TestTriggerConvenienceAliases:
    """Tests for convenience trigger aliases that pre-fill field names."""

    @pytest.mark.asyncio
    async def test_cabin_temp_trigger_converts_f_to_c(self) -> None:
        """cabin_temp.trigger converts Fahrenheit value to Celsius for storage."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch(
            {
                "method": "cabin_temp.trigger",
                "params": {"operator": "gt", "value": 72},  # 72°F
            }
        )
        assert result["field"] == "InsideTemp"
        assert result["operator"] == "gt"
        # 72°F = 22.2°C — stored value should be Celsius
        trigger = mgr.list_all()[0]
        assert trigger.condition.value == 22.2

    @pytest.mark.asyncio
    async def test_outside_temp_trigger_converts_f_to_c(self) -> None:
        """outside_temp.trigger converts Fahrenheit value to Celsius for storage."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch(
            {
                "method": "outside_temp.trigger",
                "params": {"operator": "lt", "value": 32},  # 32°F = 0°C
            }
        )
        assert result["field"] == "OutsideTemp"
        trigger = mgr.list_all()[0]
        assert trigger.condition.value == 0.0

    @pytest.mark.asyncio
    async def test_cabin_temp_trigger_fires_with_celsius_telemetry(self) -> None:
        """End-to-end: convenience alias trigger fires against real Celsius telemetry."""
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        # User sets "alert me when cabin temp > 80°F" (= 26.7°C)
        await d.dispatch(
            {
                "method": "cabin_temp.trigger",
                "params": {"operator": "gt", "value": 80, "cooldown_seconds": 0},
            }
        )
        ts = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
        # Telemetry reports 25°C (77°F) — below threshold, should NOT fire
        r1 = await mgr.evaluate("InsideTemp", 25.0, 20.0, ts)
        assert r1 is False
        # Telemetry reports 30°C (86°F) — above threshold, SHOULD fire
        r2 = await mgr.evaluate("InsideTemp", 30.0, 25.0, ts)
        assert r2 is True

    @pytest.mark.asyncio
    async def test_battery_trigger(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch(
            {
                "method": "battery.trigger",
                "params": {"operator": "lt", "value": 20},
            }
        )
        assert result["field"] == "BatteryLevel"
        # Battery is a percentage — no unit conversion
        trigger = mgr.list_all()[0]
        assert trigger.condition.value == 20

    @pytest.mark.asyncio
    async def test_location_trigger(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx, trigger_manager=mgr)
        result = await d.dispatch(
            {
                "method": "location.trigger",
                "params": {
                    "operator": "enter",
                    "value": {"latitude": 37.77, "longitude": -122.42, "radius_m": 500},
                },
            }
        )
        assert result["field"] == "Location"
        assert result["operator"] == "enter"


class TestTriggerHandlersWithoutManager:
    """Trigger handlers raise RuntimeError when no TriggerManager is wired."""

    @pytest.mark.asyncio
    async def test_trigger_create_no_manager(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(RuntimeError, match="Triggers not available"):
            await d.dispatch(
                {
                    "method": "battery.trigger",
                    "params": {"operator": "lt", "value": 20},
                }
            )

    @pytest.mark.asyncio
    async def test_trigger_delete_no_manager(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(RuntimeError, match="Triggers not available"):
            await d.dispatch(
                {"method": "battery.trigger.delete", "params": {"id": "abc"}}
            )

    @pytest.mark.asyncio
    async def test_trigger_list_no_manager(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(RuntimeError, match="Triggers not available"):
            await d.dispatch({"method": "battery.trigger.list", "params": {}})

    @pytest.mark.asyncio
    async def test_convenience_alias_no_manager(self) -> None:
        ctx = _mock_app_ctx()
        d = CommandDispatcher(vin="VIN1", app_ctx=ctx)
        with pytest.raises(RuntimeError, match="Triggers not available"):
            await d.dispatch(
                {
                    "method": "battery.trigger",
                    "params": {"operator": "lt", "value": 20},
                }
            )


class TestTriggerImmediateEvaluation:
    """Triggers that match the current telemetry value fire immediately."""

    @pytest.mark.asyncio
    async def test_trigger_fires_immediately_when_condition_met(self) -> None:
        ctx = _mock_app_ctx()
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(
            vin="VIN1", app_ctx=ctx, telemetry_store=store, trigger_manager=mgr
        )

        # Seed the store with a current battery value of 15%
        store.update("BatteryLevel", 15.0, datetime(2026, 2, 1, tzinfo=UTC))

        result = await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20}}
        )

        # Trigger fires immediately but stays registered (persistent by default)
        assert result["immediate"] is True
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_once_trigger_stays_on_immediate_fire(self) -> None:
        """One-shot trigger fires immediately but stays (pending delivery)."""
        ctx = _mock_app_ctx()
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(
            vin="VIN1", app_ctx=ctx, telemetry_store=store, trigger_manager=mgr
        )

        store.update("BatteryLevel", 15.0, datetime(2026, 2, 1, tzinfo=UTC))

        result = await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20, "once": True}}
        )

        # One-shot trigger fires immediately but is NOT deleted —
        # the push callback deletes it after confirmed WS delivery.
        assert result["immediate"] is True
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_trigger_not_immediate_when_condition_not_met(self) -> None:
        ctx = _mock_app_ctx()
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(
            vin="VIN1", app_ctx=ctx, telemetry_store=store, trigger_manager=mgr
        )

        # Battery is at 50% — trigger for < 20 should NOT fire
        store.update("BatteryLevel", 50.0, datetime(2026, 2, 1, tzinfo=UTC))

        result = await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20}}
        )

        assert "immediate" not in result
        assert len(mgr.list_all()) == 1  # trigger stays registered

    @pytest.mark.asyncio
    async def test_trigger_not_immediate_when_no_telemetry(self) -> None:
        ctx = _mock_app_ctx()
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(
            vin="VIN1", app_ctx=ctx, telemetry_store=store, trigger_manager=mgr
        )

        # No telemetry data yet — trigger should register but not fire
        result = await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20}}
        )

        assert "immediate" not in result
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_trigger_not_immediate_without_store(self) -> None:
        ctx = _mock_app_ctx()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(
            vin="VIN1", app_ctx=ctx, telemetry_store=None, trigger_manager=mgr
        )

        result = await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20}}
        )

        assert "immediate" not in result
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_immediate_fires_push_callback(self) -> None:
        """Immediate evaluation calls registered fire callbacks."""
        ctx = _mock_app_ctx()
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        d = CommandDispatcher(
            vin="VIN1", app_ctx=ctx, telemetry_store=store, trigger_manager=mgr
        )

        cb = AsyncMock()
        mgr.add_on_fire(cb)

        store.update("BatteryLevel", 15.0, datetime(2026, 2, 1, tzinfo=UTC))

        await d.dispatch(
            {"method": "battery.trigger", "params": {"operator": "lt", "value": 20}}
        )

        cb.assert_awaited_once()
        notification = cb.call_args[0][0]
        assert notification.field == "BatteryLevel"
        assert notification.value == 15.0
