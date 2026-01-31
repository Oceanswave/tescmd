"""Vehicle command API — wraps POST /api/1/vehicles/{vin}/command/{name}."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tescmd.models.command import CommandResponse

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class CommandAPI:
    """Vehicle command operations (composition over :class:`TeslaFleetClient`)."""

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def _command(
        self, vin: str, command: str, body: dict[str, Any] | None = None
    ) -> CommandResponse:
        path = f"/api/1/vehicles/{vin}/command/{command}"
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs["json"] = body
        data = await self._client.post(path, **kwargs)
        return CommandResponse.model_validate(data)

    # ------------------------------------------------------------------
    # Key enrollment
    # ------------------------------------------------------------------
    # Note: Initial key enrollment is NOT available via REST or signed_command.
    # The Tesla Go SDK explicitly blocks add_key_request for Fleet API with
    # ErrRequiresBLE. For Fleet API apps, enrollment happens through the
    # Tesla app portal flow: https://tesla.com/_ak/<domain>
    # See cli/key.py for the enrollment flow implementation.

    # ------------------------------------------------------------------
    # Charging commands
    # ------------------------------------------------------------------

    async def charge_start(self, vin: str) -> CommandResponse:
        return await self._command(vin, "charge_start")

    async def charge_stop(self, vin: str) -> CommandResponse:
        return await self._command(vin, "charge_stop")

    async def charge_standard(self, vin: str) -> CommandResponse:
        return await self._command(vin, "charge_standard")

    async def charge_max_range(self, vin: str) -> CommandResponse:
        return await self._command(vin, "charge_max_range")

    async def charge_port_door_open(self, vin: str) -> CommandResponse:
        return await self._command(vin, "charge_port_door_open")

    async def charge_port_door_close(self, vin: str) -> CommandResponse:
        return await self._command(vin, "charge_port_door_close")

    async def set_charge_limit(self, vin: str, *, percent: int) -> CommandResponse:
        return await self._command(vin, "set_charge_limit", {"percent": percent})

    async def set_charging_amps(self, vin: str, *, charging_amps: int) -> CommandResponse:
        return await self._command(vin, "set_charging_amps", {"charging_amps": charging_amps})

    async def set_scheduled_charging(
        self, vin: str, *, enable: bool, time: int
    ) -> CommandResponse:
        return await self._command(vin, "set_scheduled_charging", {"enable": enable, "time": time})

    async def set_scheduled_departure(
        self,
        vin: str,
        *,
        enable: bool,
        departure_time: int,
        preconditioning_enabled: bool = False,
        preconditioning_weekdays_only: bool = False,
        off_peak_charging_enabled: bool = False,
        off_peak_charging_weekdays_only: bool = False,
        end_off_peak_time: int = 0,
    ) -> CommandResponse:
        return await self._command(
            vin,
            "set_scheduled_departure",
            {
                "enable": enable,
                "departure_time": departure_time,
                "preconditioning_enabled": preconditioning_enabled,
                "preconditioning_weekdays_only": preconditioning_weekdays_only,
                "off_peak_charging_enabled": off_peak_charging_enabled,
                "off_peak_charging_weekdays_only": off_peak_charging_weekdays_only,
                "end_off_peak_time": end_off_peak_time,
            },
        )

    async def add_precondition_schedule(
        self, vin: str, *, schedule: dict[str, Any]
    ) -> CommandResponse:
        return await self._command(vin, "add_precondition_schedule", schedule)

    async def remove_precondition_schedule(self, vin: str, *, id: int) -> CommandResponse:
        return await self._command(vin, "remove_precondition_schedule", {"id": id})

    # ------------------------------------------------------------------
    # Climate commands
    # ------------------------------------------------------------------

    async def auto_conditioning_start(self, vin: str) -> CommandResponse:
        return await self._command(vin, "auto_conditioning_start")

    async def auto_conditioning_stop(self, vin: str) -> CommandResponse:
        return await self._command(vin, "auto_conditioning_stop")

    async def set_temps(
        self, vin: str, *, driver_temp: float, passenger_temp: float
    ) -> CommandResponse:
        return await self._command(
            vin,
            "set_temps",
            {"driver_temp": driver_temp, "passenger_temp": passenger_temp},
        )

    async def set_preconditioning_max(
        self, vin: str, *, on: bool, manual_override: bool = False
    ) -> CommandResponse:
        return await self._command(
            vin, "set_preconditioning_max", {"on": on, "manual_override": manual_override}
        )

    async def remote_seat_heater_request(
        self, vin: str, *, seat_position: int, level: int
    ) -> CommandResponse:
        return await self._command(
            vin, "remote_seat_heater_request", {"seat_position": seat_position, "level": level}
        )

    async def remote_seat_cooler_request(
        self, vin: str, *, seat_position: int, seat_cooler_level: int
    ) -> CommandResponse:
        return await self._command(
            vin,
            "remote_seat_cooler_request",
            {"seat_position": seat_position, "seat_cooler_level": seat_cooler_level},
        )

    async def remote_steering_wheel_heater_request(self, vin: str, *, on: bool) -> CommandResponse:
        return await self._command(vin, "remote_steering_wheel_heater_request", {"on": on})

    async def set_cabin_overheat_protection(
        self, vin: str, *, on: bool, fan_only: bool
    ) -> CommandResponse:
        return await self._command(
            vin,
            "set_cabin_overheat_protection",
            {"on": on, "fan_only": fan_only},
        )

    async def set_climate_keeper_mode(
        self, vin: str, *, climate_keeper_mode: int, manual_override: bool = False
    ) -> CommandResponse:
        return await self._command(
            vin,
            "set_climate_keeper_mode",
            {"climate_keeper_mode": climate_keeper_mode, "manual_override": manual_override},
        )

    async def set_cop_temp(self, vin: str, *, cop_temp: int) -> CommandResponse:
        """Set cabin overheat protection temperature (0=low, 1=medium, 2=high)."""
        return await self._command(vin, "set_cop_temp", {"cop_temp": cop_temp})

    async def remote_auto_seat_climate_request(
        self, vin: str, *, auto_seat_position: int, auto_climate_on: bool
    ) -> CommandResponse:
        return await self._command(
            vin,
            "remote_auto_seat_climate_request",
            {"auto_seat_position": auto_seat_position, "auto_climate_on": auto_climate_on},
        )

    async def remote_auto_steering_wheel_heat_climate_request(
        self, vin: str, *, on: bool
    ) -> CommandResponse:
        return await self._command(
            vin, "remote_auto_steering_wheel_heat_climate_request", {"on": on}
        )

    async def remote_steering_wheel_heat_level_request(
        self, vin: str, *, level: int
    ) -> CommandResponse:
        return await self._command(
            vin, "remote_steering_wheel_heat_level_request", {"level": level}
        )

    # ------------------------------------------------------------------
    # Security commands
    # ------------------------------------------------------------------

    async def door_lock(self, vin: str) -> CommandResponse:
        return await self._command(vin, "door_lock")

    async def door_unlock(self, vin: str) -> CommandResponse:
        return await self._command(vin, "door_unlock")

    async def set_sentry_mode(self, vin: str, *, on: bool) -> CommandResponse:
        return await self._command(vin, "set_sentry_mode", {"on": on})

    async def set_valet_mode(
        self, vin: str, *, on: bool, password: str | None = None
    ) -> CommandResponse:
        body: dict[str, Any] = {"on": on}
        if password is not None:
            body["password"] = password
        return await self._command(vin, "set_valet_mode", body)

    async def reset_valet_pin(self, vin: str) -> CommandResponse:
        return await self._command(vin, "reset_valet_pin")

    async def speed_limit_activate(self, vin: str, *, pin: str) -> CommandResponse:
        return await self._command(vin, "speed_limit_activate", {"pin": pin})

    async def speed_limit_deactivate(self, vin: str, *, pin: str) -> CommandResponse:
        return await self._command(vin, "speed_limit_deactivate", {"pin": pin})

    async def speed_limit_set_limit(self, vin: str, *, limit_mph: float) -> CommandResponse:
        return await self._command(vin, "speed_limit_set_limit", {"limit_mph": limit_mph})

    async def reset_pin_to_drive_pin(self, vin: str) -> CommandResponse:
        return await self._command(vin, "reset_pin_to_drive_pin")

    async def clear_pin_to_drive_admin(self, vin: str) -> CommandResponse:
        return await self._command(vin, "clear_pin_to_drive_admin")

    async def speed_limit_clear_pin(self, vin: str, *, pin: str) -> CommandResponse:
        return await self._command(vin, "speed_limit_clear_pin", {"pin": pin})

    async def speed_limit_clear_pin_admin(self, vin: str) -> CommandResponse:
        return await self._command(vin, "speed_limit_clear_pin_admin")

    async def remote_start_drive(self, vin: str) -> CommandResponse:
        return await self._command(vin, "remote_start_drive")

    async def flash_lights(self, vin: str) -> CommandResponse:
        return await self._command(vin, "flash_lights")

    async def honk_horn(self, vin: str) -> CommandResponse:
        return await self._command(vin, "honk_horn")

    # ------------------------------------------------------------------
    # Media commands
    # ------------------------------------------------------------------

    async def media_toggle_playback(self, vin: str) -> CommandResponse:
        return await self._command(vin, "media_toggle_playback")

    async def media_next_track(self, vin: str) -> CommandResponse:
        return await self._command(vin, "media_next_track")

    async def media_prev_track(self, vin: str) -> CommandResponse:
        return await self._command(vin, "media_prev_track")

    async def media_next_fav(self, vin: str) -> CommandResponse:
        return await self._command(vin, "media_next_fav")

    async def media_prev_fav(self, vin: str) -> CommandResponse:
        return await self._command(vin, "media_prev_fav")

    async def media_volume_up(self, vin: str) -> CommandResponse:
        return await self._command(vin, "media_volume_up")

    async def media_volume_down(self, vin: str) -> CommandResponse:
        return await self._command(vin, "media_volume_down")

    async def adjust_volume(self, vin: str, *, volume: float) -> CommandResponse:
        return await self._command(vin, "adjust_volume", {"volume": volume})

    # ------------------------------------------------------------------
    # Navigation commands
    # ------------------------------------------------------------------

    async def share(self, vin: str, *, address: str) -> CommandResponse:
        import time as _time

        body = {
            "type": "share_ext_content_raw",
            "value": {"android.intent.extra.TEXT": address},
            "locale": "en-US",
            "timestamp_ms": str(int(_time.time() * 1000)),
        }
        path = f"/api/1/vehicles/{vin}/command/share"
        data = await self._client.post(path, json=body)
        return CommandResponse.model_validate(data)

    async def navigation_gps_request(
        self, vin: str, *, lat: float, lon: float, order: int | None = None
    ) -> CommandResponse:
        body: dict[str, Any] = {"lat": lat, "lon": lon}
        if order is not None:
            body["order"] = order
        return await self._command(vin, "navigation_gps_request", body)

    async def navigation_sc_request(
        self, vin: str, *, id: int = 0, order: int = 0
    ) -> CommandResponse:
        return await self._command(vin, "navigation_sc_request", {"id": id, "order": order})

    async def trigger_homelink(self, vin: str, *, lat: float, lon: float) -> CommandResponse:
        return await self._command(vin, "trigger_homelink", {"lat": lat, "lon": lon})

    async def navigation_request(
        self,
        vin: str,
        *,
        type: str = "share_ext_content_raw",
        locale: str = "en-US",
        timestamp_ms: str = "",
        value: dict[str, Any] | None = None,
    ) -> CommandResponse:
        """Legacy navigation request (REST-only, deprecated in favour of 'share')."""
        import time as _time

        body: dict[str, Any] = {
            "type": type,
            "locale": locale,
            "timestamp_ms": timestamp_ms or str(int(_time.time() * 1000)),
        }
        if value is not None:
            body["value"] = value
        path = f"/api/1/vehicles/{vin}/command/navigation_request"
        data = await self._client.post(path, json=body)
        return CommandResponse.model_validate(data)

    async def navigation_waypoints_request(self, vin: str, *, waypoints: str) -> CommandResponse:
        return await self._command(vin, "navigation_waypoints_request", {"waypoints": waypoints})

    # ------------------------------------------------------------------
    # Software commands
    # ------------------------------------------------------------------

    async def schedule_software_update(self, vin: str, *, offset_sec: int) -> CommandResponse:
        return await self._command(vin, "schedule_software_update", {"offset_sec": offset_sec})

    async def cancel_software_update(self, vin: str) -> CommandResponse:
        return await self._command(vin, "cancel_software_update")

    # ------------------------------------------------------------------
    # Bioweapon / sunroof / PIN-to-drive / guest-mode / erase / boombox
    # ------------------------------------------------------------------

    async def set_bioweapon_mode(
        self, vin: str, *, on: bool, manual_override: bool = False
    ) -> CommandResponse:
        return await self._command(
            vin, "set_bioweapon_mode", {"on": on, "manual_override": manual_override}
        )

    async def sun_roof_control(self, vin: str, *, state: str) -> CommandResponse:
        return await self._command(vin, "sun_roof_control", {"state": state})

    async def set_pin_to_drive(
        self, vin: str, *, on: bool, password: str | None = None
    ) -> CommandResponse:
        body: dict[str, Any] = {"on": on}
        if password is not None:
            body["password"] = password
        return await self._command(vin, "set_pin_to_drive", body)

    async def guest_mode(self, vin: str, *, enable: bool) -> CommandResponse:
        return await self._command(vin, "guest_mode", {"enable": enable})

    async def erase_user_data(self, vin: str) -> CommandResponse:
        return await self._command(vin, "erase_user_data")

    async def remote_boombox(self, vin: str, *, sound: int = 2000) -> CommandResponse:
        return await self._command(vin, "remote_boombox", {"sound": sound})

    # ------------------------------------------------------------------
    # Charge schedule commands (firmware 2024.26+)
    # ------------------------------------------------------------------

    async def add_charge_schedule(self, vin: str, *, schedule: dict[str, Any]) -> CommandResponse:
        return await self._command(vin, "add_charge_schedule", schedule)

    async def remove_charge_schedule(self, vin: str, *, id: int) -> CommandResponse:
        return await self._command(vin, "remove_charge_schedule", {"id": id})

    # ------------------------------------------------------------------
    # Vehicle name / calendar
    # ------------------------------------------------------------------

    async def set_vehicle_name(self, vin: str, *, vehicle_name: str) -> CommandResponse:
        return await self._command(vin, "set_vehicle_name", {"vehicle_name": vehicle_name})

    async def upcoming_calendar_entries(self, vin: str, *, calendar_data: str) -> CommandResponse:
        return await self._command(
            vin, "upcoming_calendar_entries", {"calendar_data": calendar_data}
        )

    # ------------------------------------------------------------------
    # Trunk / window commands
    # ------------------------------------------------------------------

    async def actuate_trunk(self, vin: str, *, which_trunk: str) -> CommandResponse:
        return await self._command(vin, "actuate_trunk", {"which_trunk": which_trunk})

    async def window_control(
        self, vin: str, *, command: str, lat: float, lon: float
    ) -> CommandResponse:
        return await self._command(
            vin, "window_control", {"command": command, "lat": lat, "lon": lon}
        )

    # ------------------------------------------------------------------
    # Tonneau cover commands (Cybertruck)
    # ------------------------------------------------------------------

    async def open_tonneau(self, vin: str) -> CommandResponse:
        return await self._command(vin, "open_tonneau")

    async def close_tonneau(self, vin: str) -> CommandResponse:
        return await self._command(vin, "close_tonneau")

    async def stop_tonneau(self, vin: str) -> CommandResponse:
        return await self._command(vin, "stop_tonneau")

    # ------------------------------------------------------------------
    # Power management commands
    # ------------------------------------------------------------------

    async def set_low_power_mode(self, vin: str, *, enable: bool) -> CommandResponse:
        return await self._command(vin, "set_low_power_mode", {"enable": enable})

    async def keep_accessory_power_mode(self, vin: str, *, enable: bool) -> CommandResponse:
        return await self._command(vin, "keep_accessory_power_mode", {"enable": enable})

    # ------------------------------------------------------------------
    # Managed charging (fleet)
    # ------------------------------------------------------------------

    async def set_managed_charge_current_request(
        self, vin: str, *, charging_amps: int
    ) -> CommandResponse:
        return await self._command(
            vin, "set_managed_charge_current_request", {"charging_amps": charging_amps}
        )

    async def set_managed_charger_location(
        self, vin: str, *, location: dict[str, Any]
    ) -> CommandResponse:
        return await self._command(vin, "set_managed_charger_location", location)

    async def set_managed_scheduled_charging_time(self, vin: str, *, time: int) -> CommandResponse:
        return await self._command(vin, "set_managed_scheduled_charging_time", {"time": time})
