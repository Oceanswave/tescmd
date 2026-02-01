"""Shared telemetry field -> VehicleData path mapping.

Translates Fleet Telemetry proto field names (e.g. ``"Soc"``, ``"Location"``)
into structured VehicleData paths (e.g. ``"charge_state.usable_battery_level"``).
Used by :class:`~tescmd.telemetry.cache_sink.CacheSink` for cache warming
and available for any consumer that needs to map telemetry into the
VehicleData JSON structure.

Keys match the ``vehicle_data.proto`` Field enum names exactly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def _extract_lat(value: Any) -> float | None:
    """Extract latitude from a Location value dict."""
    try:
        return float(value["latitude"])
    except (TypeError, KeyError, ValueError):
        return None


def _extract_lon(value: Any) -> float | None:
    """Extract longitude from a Location value dict."""
    try:
        return float(value["longitude"])
    except (TypeError, KeyError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _gear_str(value: Any) -> str | None:
    """Map gear enum values to the API's shift_state strings."""
    s = str(value) if value is not None else ""
    mapping = {
        "P": "P",
        "Park": "P",
        "R": "R",
        "Reverse": "R",
        "N": "N",
        "Neutral": "N",
        "D": "D",
        "Drive": "D",
        "DriveSport": "D",
    }
    return mapping.get(s, s or None)


@dataclass(frozen=True)
class FieldMapping:
    """Maps a telemetry field to a VehicleData JSON path."""

    path: str
    """Dotted path into VehicleData (e.g. ``"charge_state.battery_level"``)."""

    transform: Any
    """Callable ``(value) -> transformed_value``. Returns ``None`` to skip."""


# ---------------------------------------------------------------------------
# Master field map: proto field name -> list of VehicleData path mappings
#
# Keys are vehicle_data.proto Field enum names.
# ---------------------------------------------------------------------------

TELEMETRY_FIELD_MAP: dict[str, list[FieldMapping]] = {
    # -- charge_state --
    "Soc": [FieldMapping("charge_state.usable_battery_level", _to_int)],
    "BatteryLevel": [FieldMapping("charge_state.battery_level", _to_int)],
    "ChargeState": [FieldMapping("charge_state.charging_state", _to_str)],
    "DetailedChargeState": [FieldMapping("charge_state.charge_port_latch", _to_str)],
    "EstBatteryRange": [FieldMapping("charge_state.est_battery_range", _to_float)],
    "IdealBatteryRange": [FieldMapping("charge_state.ideal_battery_range", _to_float)],
    "RatedRange": [FieldMapping("charge_state.battery_range", _to_float)],
    "ChargerVoltage": [FieldMapping("charge_state.charger_voltage", _to_int)],
    "ChargeAmps": [FieldMapping("charge_state.charge_amps", _to_int)],
    "ChargerPhases": [FieldMapping("charge_state.charger_phases", _to_int)],
    "ChargeLimitSoc": [FieldMapping("charge_state.charge_limit_soc", _to_int)],
    "ChargeCurrentRequest": [FieldMapping("charge_state.charge_current_request", _to_int)],
    "ChargeCurrentRequestMax": [
        FieldMapping("charge_state.charge_current_request_max", _to_int),
    ],
    "ChargePortDoorOpen": [FieldMapping("charge_state.charge_port_door_open", _to_bool)],
    "ChargePortLatch": [FieldMapping("charge_state.charge_port_latch", _to_str)],
    "TimeToFullCharge": [FieldMapping("charge_state.time_to_full_charge", _to_float)],
    "ACChargingPower": [FieldMapping("charge_state.charger_power", _to_float)],
    "ACChargingEnergyIn": [FieldMapping("charge_state.charge_energy_added", _to_float)],
    "FastChargerPresent": [FieldMapping("charge_state.fast_charger_present", _to_bool)],
    "ScheduledChargingMode": [
        FieldMapping("charge_state.scheduled_charging_mode", _to_str),
    ],
    "ScheduledChargingPending": [
        FieldMapping("charge_state.scheduled_charging_pending", _to_bool),
    ],
    "ScheduledChargingStartTime": [
        FieldMapping("charge_state.scheduled_charging_start_time", _to_float),
    ],
    "ScheduledDepartureTime": [
        FieldMapping("charge_state.scheduled_departure_time_minutes", _to_int),
    ],
    "EnergyRemaining": [FieldMapping("charge_state.energy_remaining", _to_float)],
    "PackVoltage": [FieldMapping("charge_state.pack_voltage", _to_float)],
    "PackCurrent": [FieldMapping("charge_state.pack_current", _to_float)],
    "ChargingCableType": [FieldMapping("charge_state.conn_charge_cable", _to_str)],
    # -- climate_state --
    "InsideTemp": [FieldMapping("climate_state.inside_temp", _to_float)],
    "OutsideTemp": [FieldMapping("climate_state.outside_temp", _to_float)],
    "HvacLeftTemperatureRequest": [
        FieldMapping("climate_state.driver_temp_setting", _to_float),
    ],
    "HvacRightTemperatureRequest": [
        FieldMapping("climate_state.passenger_temp_setting", _to_float),
    ],
    "HvacPower": [FieldMapping("climate_state.is_climate_on", _to_bool)],
    "HvacFanStatus": [FieldMapping("climate_state.fan_status", _to_int)],
    "SeatHeaterLeft": [FieldMapping("climate_state.seat_heater_left", _to_int)],
    "SeatHeaterRight": [FieldMapping("climate_state.seat_heater_right", _to_int)],
    "SeatHeaterRearLeft": [FieldMapping("climate_state.seat_heater_rear_left", _to_int)],
    "SeatHeaterRearCenter": [
        FieldMapping("climate_state.seat_heater_rear_center", _to_int),
    ],
    "SeatHeaterRearRight": [FieldMapping("climate_state.seat_heater_rear_right", _to_int)],
    "HvacSteeringWheelHeatLevel": [
        FieldMapping("climate_state.steering_wheel_heater", _to_bool),
    ],
    "DefrostMode": [FieldMapping("climate_state.defrost_mode", _to_int)],
    "CabinOverheatProtectionMode": [
        FieldMapping("climate_state.cabin_overheat_protection", _to_str),
    ],
    "PreconditioningEnabled": [
        FieldMapping("climate_state.is_preconditioning", _to_bool),
    ],
    # -- drive_state --
    "Location": [
        FieldMapping("drive_state.latitude", _extract_lat),
        FieldMapping("drive_state.longitude", _extract_lon),
    ],
    "VehicleSpeed": [FieldMapping("drive_state.speed", _to_int)],
    "GpsHeading": [FieldMapping("drive_state.heading", _to_int)],
    "Gear": [FieldMapping("drive_state.shift_state", _gear_str)],
    # -- vehicle_state --
    "Locked": [FieldMapping("vehicle_state.locked", _to_bool)],
    "SentryMode": [FieldMapping("vehicle_state.sentry_mode", _to_bool)],
    "Odometer": [FieldMapping("vehicle_state.odometer", _to_float)],
    "Version": [FieldMapping("vehicle_state.car_version", _to_str)],
    "ValetModeEnabled": [FieldMapping("vehicle_state.valet_mode", _to_bool)],
    "TpmsPressureFl": [FieldMapping("vehicle_state.tpms_pressure_fl", _to_float)],
    "TpmsPressureFr": [FieldMapping("vehicle_state.tpms_pressure_fr", _to_float)],
    "TpmsPressureRl": [FieldMapping("vehicle_state.tpms_pressure_rl", _to_float)],
    "TpmsPressureRr": [FieldMapping("vehicle_state.tpms_pressure_rr", _to_float)],
    "CenterDisplay": [FieldMapping("vehicle_state.center_display_state", _to_int)],
    "HomelinkNearby": [FieldMapping("vehicle_state.homelink_nearby", _to_bool)],
    "DriverSeatOccupied": [FieldMapping("vehicle_state.is_user_present", _to_bool)],
    "RemoteStartEnabled": [FieldMapping("vehicle_state.remote_start", _to_bool)],
}


class TelemetryMapper:
    """Maps telemetry field names to VehicleData paths.

    Usage::

        mapper = TelemetryMapper()
        for path, value in mapper.map("Soc", 80):
            # path = "charge_state.usable_battery_level", value = 80
            ...
    """

    def __init__(
        self,
        field_map: dict[str, list[FieldMapping]] | None = None,
    ) -> None:
        self._field_map = field_map or TELEMETRY_FIELD_MAP

    def map(self, field_name: str, value: Any) -> list[tuple[str, Any]]:
        """Map a telemetry field to zero or more ``(path, transformed_value)`` pairs.

        Returns an empty list if the field is unmapped or all transforms
        return ``None``.
        """
        mappings = self._field_map.get(field_name)
        if mappings is None:
            return []

        results: list[tuple[str, Any]] = []
        for mapping in mappings:
            try:
                transformed = mapping.transform(value)
            except Exception:
                logger.debug(
                    "Transform failed for %s -> %s",
                    field_name,
                    mapping.path,
                    exc_info=True,
                )
                continue
            if transformed is not None:
                results.append((mapping.path, transformed))
        return results

    @property
    def mapped_fields(self) -> frozenset[str]:
        """Return the set of telemetry field names that have mappings."""
        return frozenset(self._field_map.keys())
