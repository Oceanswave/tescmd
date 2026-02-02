"""Protobuf payload builders for the Vehicle Command Protocol.

Builds the ``protobuf_message_as_bytes`` content for each command.
VCSEC commands produce a serialized ``UnsignedMessage``.
Infotainment commands produce a serialized ``Action { VehicleAction { ... } }``.

Field numbers match Tesla's vehicle-command proto definitions:
  https://github.com/teslamotors/vehicle-command/tree/main/pkg/protocol/protobuf
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tescmd.protocol.protobuf.messages import (
    _encode_length_delimited,
    _encode_varint_field,
)

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

_VOID = b""  # Empty protobuf message (Void type)


def _wrap_vehicle_action(field_number: int, inner: bytes) -> bytes:
    """Wrap an inner action in VehicleAction → Action protobuf."""
    # VehicleAction { specificAction: inner }
    vehicle_action = _encode_length_delimited(field_number, inner)
    # Action { vehicleAction(field 2): vehicle_action }
    return _encode_length_delimited(2, vehicle_action)


def _void_vehicle_action(field_number: int) -> bytes:
    """Build an Action wrapping a VehicleAction with a Void field."""
    return _wrap_vehicle_action(field_number, _VOID)


# ---------------------------------------------------------------------------
# VCSEC payload builders
# ---------------------------------------------------------------------------

# UnsignedMessage field numbers (from vcsec.proto)
_VCSEC_RKE_ACTION = 2  # varint — RKEAction_E enum
_VCSEC_CLOSURE_MOVE_REQUEST = 4  # submessage — ClosureMoveRequest

# RKEAction_E enum values
_RKE_UNLOCK = 0
_RKE_LOCK = 1
_RKE_REMOTE_DRIVE = 20
_RKE_AUTO_SECURE = 29
_RKE_WAKE = 30

# ClosureMoveType_E enum values
_CLOSURE_NONE = 0
_CLOSURE_MOVE = 1
_CLOSURE_STOP = 2
_CLOSURE_OPEN = 3
_CLOSURE_CLOSE = 4

# ClosureMoveRequest field numbers
_CLOSURE_REAR_TRUNK = 5
_CLOSURE_FRONT_TRUNK = 6
_CLOSURE_CHARGE_PORT = 7
_CLOSURE_TONNEAU = 8


def _vcsec_rke(action: int) -> bytes:
    """Build UnsignedMessage with RKEAction enum."""
    return _encode_varint_field(_VCSEC_RKE_ACTION, action)


def _build_trunk_payload(body: dict[str, Any]) -> bytes:
    """Build VCSEC ClosureMoveRequest for trunk/frunk."""
    is_front = body.get("which_trunk") == "front"
    field = _CLOSURE_FRONT_TRUNK if is_front else _CLOSURE_REAR_TRUNK
    return _vcsec_closure_move(**{str(field): _CLOSURE_MOVE})


def _vcsec_closure_move(**fields: int) -> bytes:
    """Build UnsignedMessage with ClosureMoveRequest.

    Each keyword arg maps a field number to a ClosureMoveType_E value.
    """
    inner = b""
    for field_num, move_type in fields.items():
        inner += _encode_varint_field(int(field_num), move_type)
    return _encode_length_delimited(_VCSEC_CLOSURE_MOVE_REQUEST, inner)


# ---------------------------------------------------------------------------
# Infotainment (CarServer) VehicleAction field numbers
# ---------------------------------------------------------------------------

# From car_server.proto VehicleAction oneof
_VA_CHARGING_SET_LIMIT = 5
_VA_CHARGING_START_STOP = 6
_VA_DRIVING_CLEAR_SPEED_LIMIT_PIN = 7
_VA_DRIVING_SET_SPEED_LIMIT = 8
_VA_DRIVING_SPEED_LIMIT = 9
_VA_HVAC_AUTO = 10
_VA_HVAC_PRECONDITIONING_MAX = 12
_VA_HVAC_STEERING_WHEEL_HEATER = 13
_VA_HVAC_TEMP_ADJUSTMENT = 14
_VA_MEDIA_PLAY = 15
_VA_MEDIA_UPDATE_VOLUME = 16
_VA_MEDIA_NEXT_FAV = 17
_VA_MEDIA_PREV_FAV = 18
_VA_MEDIA_NEXT_TRACK = 19
_VA_MEDIA_PREV_TRACK = 20
_VA_CANCEL_SOFTWARE_UPDATE = 25
_VA_FLASH_LIGHTS = 26
_VA_HONK_HORN = 27
_VA_RESET_VALET_PIN = 28
_VA_SCHEDULE_SOFTWARE_UPDATE = 29
_VA_SET_SENTRY_MODE = 30
_VA_SET_VALET_MODE = 31
_VA_SUNROOF = 32
_VA_TRIGGER_HOMELINK = 33
_VA_WINDOW_CONTROL = 34
_VA_BIOWEAPON_MODE = 35
_VA_HVAC_SEAT_HEATER = 36
_VA_SCHEDULED_CHARGING = 41
_VA_SCHEDULED_DEPARTURE = 42
_VA_SET_CHARGING_AMPS = 43
_VA_CLIMATE_KEEPER = 44
_VA_AUTO_SEAT_CLIMATE = 48
_VA_HVAC_SEAT_COOLER = 49
_VA_SET_COP = 50
_VA_SET_VEHICLE_NAME = 54
_VA_CHARGE_PORT_CLOSE = 61
_VA_CHARGE_PORT_OPEN = 62
_VA_GUEST_MODE = 65
_VA_SET_COP_TEMP = 66
_VA_ERASE_USER_DATA = 72
_VA_SET_PIN_TO_DRIVE = 77
_VA_RESET_PIN_TO_DRIVE = 78
_VA_CLEAR_SPEED_LIMIT_PIN_ADMIN = 79
_VA_ADD_CHARGE_SCHEDULE = 97
_VA_REMOVE_CHARGE_SCHEDULE = 98
_VA_ADD_PRECONDITION_SCHEDULE = 99
_VA_REMOVE_PRECONDITION_SCHEDULE = 100
_VA_BOOMBOX = 64  # VehicleControlRemoteBoomboxAction
_VA_BATCH_REMOVE_PRECONDITION = 107
_VA_BATCH_REMOVE_CHARGE = 108
_VA_SET_LOW_POWER_MODE = 130
_VA_KEEP_ACCESSORY_POWER = 138

# Navigation (from Teslemetry's extended proto — not in Tesla's published proto)
# https://github.com/Teslemetry/python-tesla-fleet-api/blob/main/proto/car_server.proto
_VA_NAVIGATION_REQUEST = 21
_VA_NAVIGATION_SC_REQUEST = 22
_VA_NAVIGATION_GPS_REQUEST = 53
_VA_NAVIGATION_WAYPOINTS_REQUEST = 90


# ---------------------------------------------------------------------------
# Infotainment payload builders
# ---------------------------------------------------------------------------


def _charging_start_stop(body: dict[str, Any]) -> bytes:
    """ChargingStartStopAction: oneof { start=2, stop=5 }."""
    # The REST API command name determines start vs stop, not the body
    # This builder is called with the body dict which may be empty
    # The command name mapping happens in the BUILDERS dict below
    raise AssertionError("Use _charging_start or _charging_stop directly")


def _charging_start(_body: dict[str, Any]) -> bytes:
    inner = _encode_length_delimited(2, _VOID)  # start field = 2
    return _wrap_vehicle_action(_VA_CHARGING_START_STOP, inner)


def _charging_stop(_body: dict[str, Any]) -> bytes:
    inner = _encode_length_delimited(5, _VOID)  # stop field = 5
    return _wrap_vehicle_action(_VA_CHARGING_START_STOP, inner)


def _charging_standard(_body: dict[str, Any]) -> bytes:
    inner = _encode_length_delimited(3, _VOID)  # start_standard = 3
    return _wrap_vehicle_action(_VA_CHARGING_START_STOP, inner)


def _charging_max_range(_body: dict[str, Any]) -> bytes:
    inner = _encode_length_delimited(4, _VOID)  # start_max_range = 4
    return _wrap_vehicle_action(_VA_CHARGING_START_STOP, inner)


def _set_charge_limit(body: dict[str, Any]) -> bytes:
    """ChargingSetLimitAction: percent (field 1)."""
    percent = body.get("percent", 80)
    inner = _encode_varint_field(1, int(percent))
    return _wrap_vehicle_action(_VA_CHARGING_SET_LIMIT, inner)


def _set_charging_amps(body: dict[str, Any]) -> bytes:
    """SetChargingAmpsAction: charging_amps (field 1)."""
    amps = body.get("charging_amps", 32)
    inner = _encode_varint_field(1, int(amps))
    return _wrap_vehicle_action(_VA_SET_CHARGING_AMPS, inner)


def _hvac_auto(body: dict[str, Any]) -> bytes:
    """HvacAutoAction: power_on (field 1)."""
    on = body.get("power_on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    return _wrap_vehicle_action(_VA_HVAC_AUTO, inner)


def _hvac_auto_start(_body: dict[str, Any]) -> bytes:
    inner = _encode_varint_field(1, 1)  # power_on = true
    return _wrap_vehicle_action(_VA_HVAC_AUTO, inner)


def _hvac_auto_stop(_body: dict[str, Any]) -> bytes:
    inner = _encode_varint_field(1, 0)  # power_on = false
    return _wrap_vehicle_action(_VA_HVAC_AUTO, inner)


def _set_temps(body: dict[str, Any]) -> bytes:
    """HvacTemperatureAdjustmentAction: driver (field 6), passenger (field 7)."""
    inner = b""
    if "driver_temp" in body:
        # Float → fixed32 (wire type 5) is complex; use varint with *10 encoding
        # Actually Tesla uses float fields. For protobuf float, we need wire type 5.
        import struct

        driver = float(body["driver_temp"])
        inner += _encode_tag_raw(6, 5) + struct.pack("<f", driver)
    if "passenger_temp" in body:
        import struct

        passenger = float(body["passenger_temp"])
        inner += _encode_tag_raw(7, 5) + struct.pack("<f", passenger)
    return _wrap_vehicle_action(_VA_HVAC_TEMP_ADJUSTMENT, inner)


def _encode_tag_raw(field_number: int, wire_type: int) -> bytes:
    """Encode a protobuf field tag (re-export for float fields)."""
    from tescmd.protocol.protobuf.messages import _encode_tag

    return _encode_tag(field_number, wire_type)


def _set_preconditioning_max(body: dict[str, Any]) -> bytes:
    """HvacSetPreconditioningMaxAction: on (field 1), manual_override (field 2)."""
    on = body.get("on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    if body.get("manual_override"):
        inner += _encode_varint_field(2, 1)
    return _wrap_vehicle_action(_VA_HVAC_PRECONDITIONING_MAX, inner)


def _seat_heater(body: dict[str, Any]) -> bytes:
    """HvacSeatHeaterActions: hvacSeatHeaterAction (field 1, repeated submessage).

    Each sub-message has: seat_position (field 1), seat_heater_level (field 2).
    """
    seat_msg = b""
    seat_position = body.get("seat_heater", body.get("seat_position", 0))
    level = body.get("seat_heater_level", body.get("level", 0))
    seat_msg = _encode_varint_field(1, int(seat_position))
    seat_msg += _encode_varint_field(2, int(level))
    inner = _encode_length_delimited(1, seat_msg)
    return _wrap_vehicle_action(_VA_HVAC_SEAT_HEATER, inner)


def _seat_cooler(body: dict[str, Any]) -> bytes:
    """HvacSeatCoolerActions: hvacSeatCoolerAction (field 1)."""
    seat_msg = b""
    seat_position = body.get("seat_position", 0)
    level = body.get("seat_cooler_level", body.get("level", 0))
    seat_msg = _encode_varint_field(1, int(seat_position))
    seat_msg += _encode_varint_field(2, int(level))
    inner = _encode_length_delimited(1, seat_msg)
    return _wrap_vehicle_action(_VA_HVAC_SEAT_COOLER, inner)


def _steering_wheel_heater(body: dict[str, Any]) -> bytes:
    """HvacSteeringWheelHeaterAction: power_on (field 1)."""
    on = body.get("on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    return _wrap_vehicle_action(_VA_HVAC_STEERING_WHEEL_HEATER, inner)


def _set_sentry_mode(body: dict[str, Any]) -> bytes:
    """VehicleControlSetSentryModeAction: on (field 1)."""
    on = body.get("on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    return _wrap_vehicle_action(_VA_SET_SENTRY_MODE, inner)


def _set_valet_mode(body: dict[str, Any]) -> bytes:
    """VehicleControlSetValetModeAction: on (field 1), password (field 2)."""
    on = body.get("on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    if "password" in body:
        inner += _encode_length_delimited(2, str(body["password"]).encode())
    return _wrap_vehicle_action(_VA_SET_VALET_MODE, inner)


def _set_pin_to_drive(body: dict[str, Any]) -> bytes:
    """VehicleControlSetPinToDriveAction: on (field 1), password (field 2)."""
    on = body.get("on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    if "password" in body:
        inner += _encode_length_delimited(2, str(body["password"]).encode())
    return _wrap_vehicle_action(_VA_SET_PIN_TO_DRIVE, inner)


def _speed_limit_activate(body: dict[str, Any]) -> bytes:
    """DrivingSpeedLimitAction: activate (field 1) = true, pin (field 2)."""
    inner = _encode_varint_field(1, 1)
    if "pin" in body:
        inner += _encode_length_delimited(2, str(body["pin"]).encode())
    return _wrap_vehicle_action(_VA_DRIVING_SPEED_LIMIT, inner)


def _speed_limit_deactivate(body: dict[str, Any]) -> bytes:
    """DrivingSpeedLimitAction: activate (field 1) = false, pin (field 2)."""
    inner = _encode_varint_field(1, 0)
    if "pin" in body:
        inner += _encode_length_delimited(2, str(body["pin"]).encode())
    return _wrap_vehicle_action(_VA_DRIVING_SPEED_LIMIT, inner)


def _speed_limit_clear_pin(body: dict[str, Any]) -> bytes:
    """DrivingClearSpeedLimitPinAction: pin (field 1)."""
    pin = body.get("pin", "")
    inner = _encode_length_delimited(1, str(pin).encode()) if pin else _VOID
    return _wrap_vehicle_action(_VA_DRIVING_CLEAR_SPEED_LIMIT_PIN, inner)


def _speed_limit_set(body: dict[str, Any]) -> bytes:
    """DrivingSetSpeedLimitAction: limit_mph (field 1)."""
    limit = body.get("limit_mph", 65)
    inner = _encode_varint_field(1, int(limit))
    return _wrap_vehicle_action(_VA_DRIVING_SET_SPEED_LIMIT, inner)


def _media_volume(body: dict[str, Any]) -> bytes:
    """MediaUpdateVolume: volume_delta (field 1) or volume_absolute_float (field 3)."""
    inner = b""
    if "volume" in body:
        import struct

        vol = float(body["volume"])
        inner = _encode_tag_raw(3, 5) + struct.pack("<f", vol)
    elif "volume_delta" in body:
        import struct

        delta = float(body["volume_delta"])
        inner = _encode_tag_raw(1, 5) + struct.pack("<f", delta)
    return _wrap_vehicle_action(_VA_MEDIA_UPDATE_VOLUME, inner)


def _schedule_software_update(body: dict[str, Any]) -> bytes:
    """ScheduleSoftwareUpdateAction: offset_sec (field 1)."""
    offset = body.get("offset_sec", 0)
    inner = _encode_varint_field(1, int(offset))
    return _wrap_vehicle_action(_VA_SCHEDULE_SOFTWARE_UPDATE, inner)


def _sunroof(body: dict[str, Any]) -> bytes:
    """VehicleControlSunroofOpenCloseAction."""
    state = body.get("state", "")
    inner = b""
    if state == "vent":
        inner = _encode_varint_field(3, 1)  # vent = true
    elif state == "close":
        inner = _encode_varint_field(4, 1)  # close = true
    elif state == "open":
        inner = _encode_varint_field(5, 1)  # open = true
    return _wrap_vehicle_action(_VA_SUNROOF, inner)


def _trigger_homelink(body: dict[str, Any]) -> bytes:
    """VehicleControlTriggerHomelinkAction: lat/lon in LatLong submessage (field 1)."""
    lat = body.get("lat", 0.0)
    lon = body.get("lon", 0.0)
    import struct

    # LatLong message: latitude (field 1, float), longitude (field 2, float)
    location = _encode_tag_raw(1, 5) + struct.pack("<f", float(lat))
    location += _encode_tag_raw(2, 5) + struct.pack("<f", float(lon))
    inner = _encode_length_delimited(1, location)
    return _wrap_vehicle_action(_VA_TRIGGER_HOMELINK, inner)


def _set_cabin_overheat_protection(body: dict[str, Any]) -> bytes:
    """SetCabinOverheatProtectionAction: on (field 1), fan_only (field 2)."""
    on = body.get("on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    if body.get("fan_only"):
        inner += _encode_varint_field(2, 1)
    return _wrap_vehicle_action(_VA_SET_COP, inner)


def _set_climate_keeper(body: dict[str, Any]) -> bytes:
    """HvacClimateKeeperAction: ClimateKeeperAction (field 1), manual_override (field 2)."""
    action = body.get("climate_keeper_mode", 0)
    inner = _encode_varint_field(1, int(action))
    if body.get("manual_override"):
        inner += _encode_varint_field(2, 1)
    return _wrap_vehicle_action(_VA_CLIMATE_KEEPER, inner)


def _set_cop_temp(body: dict[str, Any]) -> bytes:
    """SetCopTempAction: copActivationTemp (field 1)."""
    temp = body.get("cop_temp", 0)
    inner = _encode_varint_field(1, int(temp))
    return _wrap_vehicle_action(_VA_SET_COP_TEMP, inner)


def _auto_seat_climate(body: dict[str, Any]) -> bytes:
    """AutoSeatClimateAction: carseat (field 1, repeated submessage)."""
    seat_msg = b""
    seat = body.get("auto_seat_position", body.get("seat_position", 0))
    on = body.get("on", True)
    seat_msg = _encode_varint_field(1, int(seat))
    seat_msg += _encode_varint_field(2, 1 if on else 0)
    inner = _encode_length_delimited(1, seat_msg)
    return _wrap_vehicle_action(_VA_AUTO_SEAT_CLIMATE, inner)


def _bioweapon_mode(body: dict[str, Any]) -> bytes:
    """HvacBioweaponModeAction: on (field 1), manual_override (field 2)."""
    on = body.get("on", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    if body.get("manual_override"):
        inner += _encode_varint_field(2, 1)
    return _wrap_vehicle_action(_VA_BIOWEAPON_MODE, inner)


def _window_control(body: dict[str, Any]) -> bytes:
    """VehicleControlWindowAction — vent (field 3) or close (field 4).

    Per Tesla's proto, field 1 is reserved (location removed) and the
    action is a oneof of Void fields: vent=3, close=4.
    """
    command = body.get("command", "vent")
    field = 4 if command == "close" else 3
    inner = _encode_length_delimited(field, _VOID)
    return _wrap_vehicle_action(_VA_WINDOW_CONTROL, inner)


def _set_vehicle_name(body: dict[str, Any]) -> bytes:
    """SetVehicleNameAction: vehicleName (field 1, string)."""
    name = body.get("vehicle_name", "")
    inner = _encode_length_delimited(1, str(name).encode())
    return _wrap_vehicle_action(_VA_SET_VEHICLE_NAME, inner)


def _guest_mode(body: dict[str, Any]) -> bytes:
    """GuestModeAction: enable (field 1)."""
    on = body.get("enable", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    return _wrap_vehicle_action(_VA_GUEST_MODE, inner)


def _erase_user_data(_body: dict[str, Any]) -> bytes:
    """EraseUserDataAction: reason (field 1, string)."""
    return _void_vehicle_action(_VA_ERASE_USER_DATA)


def _remote_boombox(body: dict[str, Any]) -> bytes:
    """VehicleControlRemoteBoomboxAction: action (field 1, uint32)."""
    # CLI sends {"sound": id}, protobuf field is "action"
    action = body.get("sound", body.get("action", 0))
    inner = _encode_varint_field(1, int(action))
    return _wrap_vehicle_action(_VA_BOOMBOX, inner)


def _scheduled_charging(body: dict[str, Any]) -> bytes:
    """ScheduledChargingAction."""
    inner = b""
    if "enable" in body:
        inner += _encode_varint_field(1, 1 if body["enable"] else 0)
    if "charging_time" in body:
        inner += _encode_varint_field(2, int(body["charging_time"]))
    return _wrap_vehicle_action(_VA_SCHEDULED_CHARGING, inner)


def _scheduled_departure(body: dict[str, Any]) -> bytes:
    """ScheduledDepartureAction."""
    inner = b""
    if "enable" in body:
        inner += _encode_varint_field(1, 1 if body["enable"] else 0)
    if "departure_time" in body:
        inner += _encode_varint_field(2, int(body["departure_time"]))
    return _wrap_vehicle_action(_VA_SCHEDULED_DEPARTURE, inner)


def _add_charge_schedule(body: dict[str, Any]) -> bytes:
    """AddChargeScheduleAction — pass through body fields."""
    inner = b""
    # Schedule ID, start time, end time, etc. are encoded as varint fields
    for key, field_num in [("id", 1), ("start_time", 2), ("end_time", 3)]:
        if key in body:
            inner += _encode_varint_field(field_num, int(body[key]))
    return _wrap_vehicle_action(_VA_ADD_CHARGE_SCHEDULE, inner)


def _remove_charge_schedule(body: dict[str, Any]) -> bytes:
    """RemoveChargeScheduleAction: id (field 1)."""
    schedule_id = body.get("id", 0)
    inner = _encode_varint_field(1, int(schedule_id))
    return _wrap_vehicle_action(_VA_REMOVE_CHARGE_SCHEDULE, inner)


def _add_precondition_schedule(body: dict[str, Any]) -> bytes:
    """AddPreconditionScheduleAction."""
    inner = b""
    for key, field_num in [("id", 1), ("start_time", 2), ("end_time", 3)]:
        if key in body:
            inner += _encode_varint_field(field_num, int(body[key]))
    return _wrap_vehicle_action(_VA_ADD_PRECONDITION_SCHEDULE, inner)


def _remove_precondition_schedule(body: dict[str, Any]) -> bytes:
    """RemovePreconditionScheduleAction: id (field 1)."""
    schedule_id = body.get("id", 0)
    inner = _encode_varint_field(1, int(schedule_id))
    return _wrap_vehicle_action(_VA_REMOVE_PRECONDITION_SCHEDULE, inner)


def _steering_wheel_heat_level(body: dict[str, Any]) -> bytes:
    """HvacSteeringWheelHeaterAction with level."""
    level = body.get("level", 0)
    inner = _encode_varint_field(1, int(level))
    return _wrap_vehicle_action(_VA_HVAC_STEERING_WHEEL_HEATER, inner)


def _set_low_power_mode(body: dict[str, Any]) -> bytes:
    """SetLowPowerModeAction: low_power_mode (field 1, bool)."""
    on = body.get("enable", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    return _wrap_vehicle_action(_VA_SET_LOW_POWER_MODE, inner)


def _keep_accessory_power_mode(body: dict[str, Any]) -> bytes:
    """SetKeepAccessoryPowerModeAction: keep_accessory_power_mode (field 1, bool)."""
    on = body.get("enable", True)
    inner = _encode_varint_field(1, 1 if on else 0)
    return _wrap_vehicle_action(_VA_KEEP_ACCESSORY_POWER, inner)


def _batch_remove_precondition_schedules(body: dict[str, Any]) -> bytes:
    """BatchRemovePreconditionSchedulesAction: home(1), work(2), other(3)."""
    inner = b""
    if body.get("home"):
        inner += _encode_varint_field(1, 1)
    if body.get("work"):
        inner += _encode_varint_field(2, 1)
    if body.get("other"):
        inner += _encode_varint_field(3, 1)
    return _wrap_vehicle_action(_VA_BATCH_REMOVE_PRECONDITION, inner)


def _batch_remove_charge_schedules(body: dict[str, Any]) -> bytes:
    """BatchRemoveChargeSchedulesAction: home(1), work(2), other(3)."""
    inner = b""
    if body.get("home"):
        inner += _encode_varint_field(1, 1)
    if body.get("work"):
        inner += _encode_varint_field(2, 1)
    if body.get("other"):
        inner += _encode_varint_field(3, 1)
    return _wrap_vehicle_action(_VA_BATCH_REMOVE_CHARGE, inner)


# ---------------------------------------------------------------------------
# Navigation payload builders
# ---------------------------------------------------------------------------


def _navigation_request(body: dict[str, Any]) -> bytes:
    """NavigationRequest: destination (field 1, string), order (field 2, int32).

    The CLI ``nav send`` command passes ``{"address": "..."}``.  The REST
    ``share`` endpoint wraps this in an Android intent JSON, but the VCP
    proto only needs the destination string.
    """
    inner = b""
    destination = body.get("address", body.get("destination", ""))
    if destination:
        inner += _encode_length_delimited(1, str(destination).encode())
    order = body.get("order")
    if order is not None:
        inner += _encode_varint_field(2, int(order))
    return _wrap_vehicle_action(_VA_NAVIGATION_REQUEST, inner)


def _navigation_sc_request(body: dict[str, Any]) -> bytes:
    """NavigationSuperchargerRequest: order (field 1, int32)."""
    order = body.get("order", 1)
    inner = _encode_varint_field(1, int(order))
    return _wrap_vehicle_action(_VA_NAVIGATION_SC_REQUEST, inner)


def _navigation_gps_request(body: dict[str, Any]) -> bytes:
    """NavigationGpsRequest: lat (1, double), lon (2, double), order (3, enum)."""
    import struct

    inner = b""
    lat = body.get("lat", 0.0)
    lon = body.get("lon", 0.0)
    # Protobuf double = wire type 1 (fixed 64-bit)
    inner += _encode_tag_raw(1, 1) + struct.pack("<d", float(lat))
    inner += _encode_tag_raw(2, 1) + struct.pack("<d", float(lon))
    order = body.get("order")
    if order is not None:
        inner += _encode_varint_field(3, int(order))
    return _wrap_vehicle_action(_VA_NAVIGATION_GPS_REQUEST, inner)


def _navigation_waypoints_request(body: dict[str, Any]) -> bytes:
    """NavigationWaypointsRequest: waypoints (field 1, string)."""
    inner = b""
    waypoints = body.get("waypoints", "")
    if waypoints:
        inner += _encode_length_delimited(1, str(waypoints).encode())
    return _wrap_vehicle_action(_VA_NAVIGATION_WAYPOINTS_REQUEST, inner)


# ---------------------------------------------------------------------------
# Builder registry — maps REST command names to payload builder functions
# ---------------------------------------------------------------------------

_PayloadBuilder = Callable[[dict[str, Any]], bytes]

_BUILDERS: dict[str, _PayloadBuilder] = {
    # VCSEC commands → UnsignedMessage payloads
    "door_lock": lambda _: _vcsec_rke(_RKE_LOCK),
    "door_unlock": lambda _: _vcsec_rke(_RKE_UNLOCK),
    "remote_start_drive": lambda _: _vcsec_rke(_RKE_REMOTE_DRIVE),
    "auto_secure_vehicle": lambda _: _vcsec_rke(_RKE_AUTO_SECURE),
    "actuate_trunk": lambda body: _build_trunk_payload(body),
    "open_tonneau": lambda _: _vcsec_closure_move(**{str(_CLOSURE_TONNEAU): _CLOSURE_OPEN}),
    "close_tonneau": lambda _: _vcsec_closure_move(**{str(_CLOSURE_TONNEAU): _CLOSURE_CLOSE}),
    "stop_tonneau": lambda _: _vcsec_closure_move(**{str(_CLOSURE_TONNEAU): _CLOSURE_STOP}),
    # Infotainment commands → Action { VehicleAction } payloads
    "charge_start": _charging_start,
    "charge_stop": _charging_stop,
    "charge_standard": _charging_standard,
    "charge_max_range": _charging_max_range,
    "charge_port_door_open": lambda _: _void_vehicle_action(_VA_CHARGE_PORT_OPEN),
    "charge_port_door_close": lambda _: _void_vehicle_action(_VA_CHARGE_PORT_CLOSE),
    "set_charge_limit": _set_charge_limit,
    "set_charging_amps": _set_charging_amps,
    "set_scheduled_charging": _scheduled_charging,
    "set_scheduled_departure": _scheduled_departure,
    "add_charge_schedule": _add_charge_schedule,
    "remove_charge_schedule": _remove_charge_schedule,
    "add_precondition_schedule": _add_precondition_schedule,
    "remove_precondition_schedule": _remove_precondition_schedule,
    "batch_remove_precondition_schedules": _batch_remove_precondition_schedules,
    "batch_remove_charge_schedules": _batch_remove_charge_schedules,
    # Climate
    "auto_conditioning_start": _hvac_auto_start,
    "auto_conditioning_stop": _hvac_auto_stop,
    "set_temps": _set_temps,
    "set_preconditioning_max": _set_preconditioning_max,
    "remote_seat_heater_request": _seat_heater,
    "remote_seat_cooler_request": _seat_cooler,
    "remote_steering_wheel_heater_request": _steering_wheel_heater,
    "set_cabin_overheat_protection": _set_cabin_overheat_protection,
    "set_climate_keeper_mode": _set_climate_keeper,
    "set_cop_temp": _set_cop_temp,
    "remote_auto_seat_climate_request": _auto_seat_climate,
    "remote_auto_steering_wheel_heat_climate_request": _steering_wheel_heater,
    "remote_steering_wheel_heat_level_request": _steering_wheel_heat_level,
    "set_bioweapon_mode": _bioweapon_mode,
    # Security (infotainment-routed)
    "set_sentry_mode": _set_sentry_mode,
    "set_valet_mode": _set_valet_mode,
    "reset_valet_pin": lambda _: _void_vehicle_action(_VA_RESET_VALET_PIN),
    "speed_limit_activate": _speed_limit_activate,
    "speed_limit_deactivate": _speed_limit_deactivate,
    "speed_limit_set_limit": _speed_limit_set,
    "speed_limit_clear_pin": lambda body: _speed_limit_clear_pin(body),
    "reset_pin_to_drive_pin": lambda _: _void_vehicle_action(_VA_RESET_PIN_TO_DRIVE),
    "clear_pin_to_drive_admin": lambda _: _void_vehicle_action(_VA_RESET_PIN_TO_DRIVE),
    "speed_limit_clear_pin_admin": lambda _: _void_vehicle_action(_VA_CLEAR_SPEED_LIMIT_PIN_ADMIN),
    "honk_horn": lambda _: _void_vehicle_action(_VA_HONK_HORN),
    "flash_lights": lambda _: _void_vehicle_action(_VA_FLASH_LIGHTS),
    "set_pin_to_drive": _set_pin_to_drive,
    "guest_mode": _guest_mode,
    "erase_user_data": _erase_user_data,
    "remote_boombox": _remote_boombox,
    # Media
    "media_toggle_playback": lambda _: _void_vehicle_action(_VA_MEDIA_PLAY),
    "media_next_track": lambda _: _void_vehicle_action(_VA_MEDIA_NEXT_TRACK),
    "media_prev_track": lambda _: _void_vehicle_action(_VA_MEDIA_PREV_TRACK),
    "media_next_fav": lambda _: _void_vehicle_action(_VA_MEDIA_NEXT_FAV),
    "media_prev_fav": lambda _: _void_vehicle_action(_VA_MEDIA_PREV_FAV),
    "media_volume_up": lambda body: _media_volume(
        {"volume_delta": body.get("volume_delta", 0.5)},
    ),
    "media_volume_down": lambda body: _media_volume(
        {"volume_delta": body.get("volume_delta", -0.5)},
    ),
    "adjust_volume": _media_volume,
    # Navigation
    "share": _navigation_request,
    "navigation_gps_request": _navigation_gps_request,
    "navigation_sc_request": _navigation_sc_request,
    "navigation_waypoints_request": _navigation_waypoints_request,
    "trigger_homelink": _trigger_homelink,
    # Software
    "schedule_software_update": _schedule_software_update,
    "cancel_software_update": lambda _: _void_vehicle_action(_VA_CANCEL_SOFTWARE_UPDATE),
    # Vehicle
    "set_vehicle_name": _set_vehicle_name,
    # Sunroof
    "sun_roof_control": _sunroof,
    # Window (infotainment path)
    "window_control": _window_control,
    # Power management
    "set_low_power_mode": _set_low_power_mode,
    "keep_accessory_power_mode": _keep_accessory_power_mode,
}


def build_command_payload(command: str, body: dict[str, Any] | None) -> bytes:
    """Build the protobuf payload for a vehicle command.

    Returns serialized bytes suitable for ``protobuf_message_as_bytes``
    in a :class:`RoutableMessage`.

    Raises :class:`ValueError` if no builder exists for the command.
    """
    builder = _BUILDERS.get(command)
    if builder is None:
        raise ValueError(
            f"No protobuf payload builder for command '{command}'. "
            "This command may not be supported via the Vehicle Command Protocol."
        )
    return builder(body or {})
