"""Tests for tescmd.api.command — CommandAPI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tescmd.api.command import CommandAPI
from tescmd.models.command import CommandResponse

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tescmd.api.client import TeslaFleetClient

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"

_OK_RESPONSE = {"response": {"result": True, "reason": ""}}
_FAIL_RESPONSE = {"response": {"result": False, "reason": "vehicle is asleep"}}


def _body(mock: HTTPXMock, idx: int = 0) -> dict[str, object]:
    """Parse the JSON body of the idx-th request."""
    return json.loads(mock.get_requests()[idx].content)  # type: ignore[no-any-return]


class TestChargeCommands:
    @pytest.mark.asyncio
    async def test_charge_start(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/command/charge_start",
            json=_OK_RESPONSE,
        )
        api = CommandAPI(mock_client)
        result = await api.charge_start(VIN)

        assert isinstance(result, CommandResponse)
        assert result.response.result is True

    @pytest.mark.asyncio
    async def test_set_charge_limit_sends_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_charge_limit(VIN, percent=80)

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/vehicles/{VIN}/command/set_charge_limit"
        assert _body(httpx_mock)["percent"] == 80

    @pytest.mark.asyncio
    async def test_set_charging_amps_sends_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_charging_amps(VIN, charging_amps=32)

        assert _body(httpx_mock)["charging_amps"] == 32

    @pytest.mark.asyncio
    async def test_set_scheduled_charging_sends_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_scheduled_charging(VIN, enable=True, time=480)

        body = _body(httpx_mock)
        assert body["enable"] is True
        assert body["time"] == 480

    @pytest.mark.asyncio
    async def test_command_failure_response(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_FAIL_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.charge_start(VIN)

        assert result.response.result is False
        assert result.response.reason == "vehicle is asleep"


class TestClimateCommands:
    @pytest.mark.asyncio
    async def test_set_temps_sends_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_temps(VIN, driver_temp=22.0, passenger_temp=20.0)

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/vehicles/{VIN}/command/set_temps"
        body = _body(httpx_mock)
        assert body["driver_temp"] == 22.0
        assert body["passenger_temp"] == 20.0

    @pytest.mark.asyncio
    async def test_remote_seat_heater_request(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.remote_seat_heater_request(VIN, seat_position=0, level=3)

        body = _body(httpx_mock)
        assert body["seat_position"] == 0
        assert body["level"] == 3

    @pytest.mark.asyncio
    async def test_set_climate_keeper_mode(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_climate_keeper_mode(VIN, climate_keeper_mode=2)

        assert _body(httpx_mock)["climate_keeper_mode"] == 2


class TestCabinOverheatProtection:
    @pytest.mark.asyncio
    async def test_fan_only_defaults_false(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_cabin_overheat_protection(VIN, on=True)

        body = _body(httpx_mock)
        assert body["on"] is True
        assert body["fan_only"] is False

    @pytest.mark.asyncio
    async def test_fan_only_explicit_true(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_cabin_overheat_protection(VIN, on=True, fan_only=True)

        body = _body(httpx_mock)
        assert body["on"] is True
        assert body["fan_only"] is True


class TestSecurityCommands:
    @pytest.mark.asyncio
    async def test_door_lock_no_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/command/door_lock",
            json=_OK_RESPONSE,
        )
        api = CommandAPI(mock_client)
        result = await api.door_lock(VIN)

        assert result.response.result is True
        request = httpx_mock.get_requests()[0]
        # No body for lock
        assert request.content == b""

    @pytest.mark.asyncio
    async def test_set_sentry_mode_sends_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_sentry_mode(VIN, on=True)

        assert _body(httpx_mock)["on"] is True

    @pytest.mark.asyncio
    async def test_set_valet_mode_with_password(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_valet_mode(VIN, on=True, password="1234")

        body = _body(httpx_mock)
        assert body["on"] is True
        assert body["password"] == "1234"

    @pytest.mark.asyncio
    async def test_speed_limit_activate(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.speed_limit_activate(VIN, pin="1234")

        assert _body(httpx_mock)["pin"] == "1234"


class TestTrunkCommands:
    @pytest.mark.asyncio
    async def test_actuate_trunk_sends_which(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.actuate_trunk(VIN, which_trunk="rear")

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/vehicles/{VIN}/command/actuate_trunk"
        assert _body(httpx_mock)["which_trunk"] == "rear"

    @pytest.mark.asyncio
    async def test_window_control_sends_params(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.window_control(VIN, command="vent", lat=0.0, lon=0.0)

        body = _body(httpx_mock)
        assert body["command"] == "vent"
        assert body["lat"] == 0.0
        assert body["lon"] == 0.0


# ------------------------------------------------------------------
# Phase 4: New command tests
# ------------------------------------------------------------------


class TestHomelinkCommands:
    @pytest.mark.asyncio
    async def test_trigger_homelink(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.trigger_homelink(VIN, lat=37.77, lon=-122.42)

        assert result.response.result is True
        body = _body(httpx_mock)
        assert body["lat"] == 37.77
        assert body["lon"] == -122.42


class TestScheduledDeparture:
    @pytest.mark.asyncio
    async def test_set_scheduled_departure(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_scheduled_departure(
            VIN,
            enable=True,
            departure_time=480,
            preconditioning_enabled=True,
            off_peak_charging_enabled=True,
            end_off_peak_time=360,
        )

        body = _body(httpx_mock)
        assert body["enable"] is True
        assert body["departure_time"] == 480
        assert body["preconditioning_enabled"] is True
        assert body["off_peak_charging_enabled"] is True
        assert body["end_off_peak_time"] == 360


class TestChargeSchedule:
    @pytest.mark.asyncio
    async def test_add_charge_schedule_with_params(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.add_charge_schedule(
            VIN, id=1, enabled=True, start_time=360, end_time=480, days_of_week="0111110"
        )

        body = _body(httpx_mock)
        assert body["id"] == 1
        assert body["enabled"] is True
        assert body["start_time"] == 360
        assert body["days_of_week"] == "0111110"

    @pytest.mark.asyncio
    async def test_add_charge_schedule_omits_none_params(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.add_charge_schedule(VIN, id=1, enabled=True)

        body = _body(httpx_mock)
        assert body == {"id": 1, "enabled": True}

    @pytest.mark.asyncio
    async def test_remove_charge_schedule(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.remove_charge_schedule(VIN, id=1)

        assert _body(httpx_mock)["id"] == 1


class TestPreconditionSchedule:
    @pytest.mark.asyncio
    async def test_add_precondition_schedule_with_params(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.add_precondition_schedule(
            VIN, id=1, enabled=True, days_of_week="1111111"
        )

        body = _body(httpx_mock)
        assert body["id"] == 1
        assert body["enabled"] is True
        assert body["days_of_week"] == "1111111"

    @pytest.mark.asyncio
    async def test_add_precondition_schedule_omits_none_params(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.add_precondition_schedule(VIN, id=2, enabled=False)

        body = _body(httpx_mock)
        assert body == {"id": 2, "enabled": False}

    @pytest.mark.asyncio
    async def test_remove_precondition_schedule(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.remove_precondition_schedule(VIN, id=1)

        assert _body(httpx_mock)["id"] == 1


class TestClimateNewCommands:
    @pytest.mark.asyncio
    async def test_set_cop_temp(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_cop_temp(VIN, cop_temp=2)

        assert _body(httpx_mock)["cop_temp"] == 2

    @pytest.mark.asyncio
    async def test_remote_auto_seat_climate(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.remote_auto_seat_climate_request(VIN, auto_seat_position=0, auto_climate_on=True)

        body = _body(httpx_mock)
        assert body["auto_seat_position"] == 0
        assert body["auto_climate_on"] is True

    @pytest.mark.asyncio
    async def test_remote_auto_steering_wheel_heat(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.remote_auto_steering_wheel_heat_climate_request(VIN, on=True)

        assert _body(httpx_mock)["on"] is True

    @pytest.mark.asyncio
    async def test_steering_wheel_heat_level(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.remote_steering_wheel_heat_level_request(VIN, level=3)

        assert _body(httpx_mock)["level"] == 3


class TestSecurityNewCommands:
    @pytest.mark.asyncio
    async def test_reset_pin_to_drive_pin(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.reset_pin_to_drive_pin(VIN)

        assert result.response.result is True
        request = httpx_mock.get_requests()[0]
        assert request.content == b""

    @pytest.mark.asyncio
    async def test_clear_pin_to_drive_admin(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.clear_pin_to_drive_admin(VIN)

        assert result.response.result is True

    @pytest.mark.asyncio
    async def test_speed_limit_clear_pin(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.speed_limit_clear_pin(VIN, pin="1234")

        assert _body(httpx_mock)["pin"] == "1234"

    @pytest.mark.asyncio
    async def test_speed_limit_clear_pin_admin(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.speed_limit_clear_pin_admin(VIN)

        assert result.response.result is True


class TestNavigationNewCommands:
    @pytest.mark.asyncio
    async def test_navigation_waypoints(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        waypoints_str = "refId:ChIJIQBpAG2ahYAR_6128GcTUEo,refId:ChIJw____96GhYARCVVwg5cT7c0"
        await api.navigation_waypoints_request(VIN, waypoints=waypoints_str)

        body = _body(httpx_mock)
        assert body["waypoints"] == waypoints_str
        assert "navigation_waypoints_request" in str(httpx_mock.get_requests()[0].url)


class TestNavigationScRequest:
    @pytest.mark.asyncio
    async def test_navigation_sc_request_with_params(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.navigation_sc_request(VIN, id=42, order=1)

        body = _body(httpx_mock)
        assert body["id"] == 42
        assert body["order"] == 1
        assert "navigation_sc_request" in str(httpx_mock.get_requests()[0].url)

    @pytest.mark.asyncio
    async def test_navigation_sc_request_defaults(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.navigation_sc_request(VIN)

        body = _body(httpx_mock)
        assert body["id"] == 0
        assert body["order"] == 0


class TestBoomboxCommand:
    @pytest.mark.asyncio
    async def test_remote_boombox_default_sound(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.remote_boombox(VIN)

        assert result.response.result is True
        body = _body(httpx_mock)
        assert body["sound"] == 2000

    @pytest.mark.asyncio
    async def test_remote_boombox_fart_sound(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.remote_boombox(VIN, sound=0)

        body = _body(httpx_mock)
        assert body["sound"] == 0


class TestSpeedLimitFloat:
    @pytest.mark.asyncio
    async def test_speed_limit_set_limit_float(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.speed_limit_set_limit(VIN, limit_mph=65.5)

        body = _body(httpx_mock)
        assert body["limit_mph"] == 65.5

    @pytest.mark.asyncio
    async def test_speed_limit_set_limit_int_still_works(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.speed_limit_set_limit(VIN, limit_mph=65)

        body = _body(httpx_mock)
        assert body["limit_mph"] == 65


class TestTonneauCommands:
    @pytest.mark.asyncio
    async def test_open_tonneau(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.open_tonneau(VIN)

        assert result.response.result is True
        request = httpx_mock.get_requests()[0]
        assert "open_tonneau" in str(request.url)
        assert request.content == b""

    @pytest.mark.asyncio
    async def test_close_tonneau(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.close_tonneau(VIN)

        assert result.response.result is True
        assert "close_tonneau" in str(httpx_mock.get_requests()[0].url)

    @pytest.mark.asyncio
    async def test_stop_tonneau(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.stop_tonneau(VIN)

        assert result.response.result is True
        assert "stop_tonneau" in str(httpx_mock.get_requests()[0].url)


class TestPowerManagementCommands:
    @pytest.mark.asyncio
    async def test_set_low_power_mode_on(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.set_low_power_mode(VIN, enable=True)

        assert result.response.result is True
        assert _body(httpx_mock)["enable"] is True

    @pytest.mark.asyncio
    async def test_set_low_power_mode_off(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.set_low_power_mode(VIN, enable=False)

        assert _body(httpx_mock)["enable"] is False

    @pytest.mark.asyncio
    async def test_keep_accessory_power_mode_on(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.keep_accessory_power_mode(VIN, enable=True)

        assert result.response.result is True
        assert _body(httpx_mock)["enable"] is True

    @pytest.mark.asyncio
    async def test_keep_accessory_power_mode_off(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.keep_accessory_power_mode(VIN, enable=False)

        assert _body(httpx_mock)["enable"] is False


class TestManagedChargingCommand:
    @pytest.mark.asyncio
    async def test_set_managed_charge_current_request(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.set_managed_charge_current_request(VIN, charging_amps=16)

        assert result.response.result is True
        body = _body(httpx_mock)
        assert body["charging_amps"] == 16
        assert "set_managed_charge_current_request" in str(httpx_mock.get_requests()[0].url)


class TestNavigationRequest:
    @pytest.mark.asyncio
    async def test_navigation_request_sends_correct_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.navigation_request(
            VIN, value={"android.intent.extra.TEXT": "123 Main St"}
        )

        assert result.response.result is True
        body = _body(httpx_mock)
        assert body["type"] == "share_ext_content_raw"
        assert body["locale"] == "en-US"
        assert "timestamp_ms" in body
        assert body["value"] == {"android.intent.extra.TEXT": "123 Main St"}
        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/vehicles/{VIN}/command/navigation_request"


class TestManagedChargingExtended:
    @pytest.mark.asyncio
    async def test_set_managed_charger_location(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.set_managed_charger_location(
            VIN, location={"lat": 37.77, "lon": -122.42}
        )

        assert result.response.result is True
        body = _body(httpx_mock)
        assert body["lat"] == 37.77
        assert body["lon"] == -122.42
        assert "set_managed_charger_location" in str(httpx_mock.get_requests()[0].url)

    @pytest.mark.asyncio
    async def test_set_managed_scheduled_charging_time(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.set_managed_scheduled_charging_time(VIN, time=480)

        assert result.response.result is True
        assert _body(httpx_mock) == {"time": 480}


class TestAdjustVolumeFloat:
    @pytest.mark.asyncio
    async def test_adjust_volume_sends_float(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        await api.adjust_volume(VIN, volume=5.5)

        body = _body(httpx_mock)
        assert body["volume"] == 5.5
        assert isinstance(body["volume"], float)


class TestPreconditioningManualOverride:
    @pytest.mark.asyncio
    async def test_set_preconditioning_max_with_manual_override(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.set_preconditioning_max(VIN, on=True, manual_override=True)

        assert result.response.result is True
        body = _body(httpx_mock)
        assert body["on"] is True
        assert body["manual_override"] is True


class TestClimateKeeperManualOverride:
    @pytest.mark.asyncio
    async def test_set_climate_keeper_mode_with_manual_override(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json=_OK_RESPONSE)
        api = CommandAPI(mock_client)
        result = await api.set_climate_keeper_mode(
            VIN, climate_keeper_mode=2, manual_override=True
        )

        assert result.response.result is True
        body = _body(httpx_mock)
        assert body["climate_keeper_mode"] == 2
        assert body["manual_override"] is True
