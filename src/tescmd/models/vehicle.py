from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_EXTRA_ALLOW = ConfigDict(extra="allow")


class Vehicle(BaseModel):
    model_config = _EXTRA_ALLOW

    vin: str
    display_name: str | None = None
    state: str = "unknown"
    vehicle_id: int | None = None
    access_type: str | None = None


class DriveState(BaseModel):
    model_config = _EXTRA_ALLOW

    latitude: float | None = None
    longitude: float | None = None
    heading: int | None = None
    speed: int | None = None
    power: int | None = None
    shift_state: str | None = None
    timestamp: int | None = None


class ChargeState(BaseModel):
    model_config = _EXTRA_ALLOW

    battery_level: int | None = None
    battery_range: float | None = None
    charge_limit_soc: int | None = None
    charging_state: str | None = None
    charge_rate: float | None = None
    charger_voltage: int | None = None
    charger_actual_current: int | None = None
    charge_port_door_open: bool | None = None
    minutes_to_full_charge: int | None = None
    scheduled_charging_start_time: int | None = None
    charger_type: str | None = None


class ClimateState(BaseModel):
    model_config = _EXTRA_ALLOW

    inside_temp: float | None = None
    outside_temp: float | None = None
    driver_temp_setting: float | None = None
    passenger_temp_setting: float | None = None
    is_climate_on: bool | None = None
    fan_status: int | None = None
    defrost_mode: int | None = None
    seat_heater_left: int | None = None
    seat_heater_right: int | None = None
    steering_wheel_heater: bool | None = None


class VehicleState(BaseModel):
    model_config = _EXTRA_ALLOW

    locked: bool | None = None
    odometer: float | None = None
    sentry_mode: bool | None = None
    car_version: str | None = None
    door_driver_front: int | None = None
    door_driver_rear: int | None = None
    door_passenger_front: int | None = None
    door_passenger_rear: int | None = None
    window_driver_front: int | None = None
    window_driver_rear: int | None = None
    window_passenger_front: int | None = None
    window_passenger_rear: int | None = None


class VehicleConfig(BaseModel):
    model_config = _EXTRA_ALLOW

    car_type: str | None = None
    trim_badging: str | None = None
    exterior_color: str | None = None
    wheel_type: str | None = None


class GuiSettings(BaseModel):
    model_config = _EXTRA_ALLOW

    gui_distance_units: str | None = None
    gui_temperature_units: str | None = None
    gui_charge_rate_units: str | None = None


class VehicleData(BaseModel):
    model_config = _EXTRA_ALLOW

    vin: str
    display_name: str | None = None
    state: str = "unknown"
    vehicle_id: int | None = None
    charge_state: ChargeState | None = None
    climate_state: ClimateState | None = None
    drive_state: DriveState | None = None
    vehicle_state: VehicleState | None = None
    vehicle_config: VehicleConfig | None = None
    gui_settings: GuiSettings | None = None
