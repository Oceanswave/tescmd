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
    ideal_battery_range: float | None = None
    est_battery_range: float | None = None
    usable_battery_level: int | None = None
    charge_energy_added: float | None = None
    charge_miles_added_rated: float | None = None
    charger_power: int | None = None
    time_to_full_charge: float | None = None
    scheduled_charging_mode: str | None = None
    scheduled_departure_time_minutes: int | None = None
    preconditioning_enabled: bool | None = None
    battery_heater_on: bool | None = None
    charge_port_latch: str | None = None
    conn_charge_cable: str | None = None


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
    cabin_overheat_protection: str | None = None
    cabin_overheat_protection_actively_cooling: bool | None = None
    is_auto_conditioning_on: bool | None = None
    is_preconditioning: bool | None = None
    seat_heater_rear_left: int | None = None
    seat_heater_rear_center: int | None = None
    seat_heater_rear_right: int | None = None
    bioweapon_defense_mode: bool | None = None


class SoftwareUpdateInfo(BaseModel):
    model_config = _EXTRA_ALLOW

    status: str | None = None
    version: str | None = None
    install_perc: int | None = None
    expected_duration_sec: int | None = None
    scheduled_time_ms: int | None = None
    download_perc: int | None = None


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
    ft: int | None = None
    rt: int | None = None
    homelink_nearby: bool | None = None
    is_user_present: bool | None = None
    center_display_state: int | None = None
    dashcam_state: str | None = None
    remote_start_enabled: bool | None = None
    tpms_pressure_fl: float | None = None
    tpms_pressure_fr: float | None = None
    tpms_pressure_rl: float | None = None
    tpms_pressure_rr: float | None = None
    software_update: SoftwareUpdateInfo | None = None


class VehicleConfig(BaseModel):
    model_config = _EXTRA_ALLOW

    car_type: str | None = None
    trim_badging: str | None = None
    exterior_color: str | None = None
    wheel_type: str | None = None
    can_accept_navigation_requests: bool | None = None
    can_actuate_trunks: bool | None = None
    eu_vehicle: bool | None = None
    has_seat_cooling: bool | None = None
    motorized_charge_port: bool | None = None
    plg: bool | None = None
    roof_color: str | None = None


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


class SuperchargerInfo(BaseModel):
    model_config = _EXTRA_ALLOW

    name: str | None = None
    location: dict[str, float] | None = None
    distance_miles: float | None = None
    total_stalls: int | None = None
    available_stalls: int | None = None


class DestChargerInfo(BaseModel):
    model_config = _EXTRA_ALLOW

    name: str | None = None
    location: dict[str, float] | None = None
    distance_miles: float | None = None


class NearbyChargingSites(BaseModel):
    model_config = _EXTRA_ALLOW

    superchargers: list[SuperchargerInfo] = []
    destination_charging: list[DestChargerInfo] = []
    congestion_sync_time_utc_secs: int | None = None
    timestamp: int | None = None
