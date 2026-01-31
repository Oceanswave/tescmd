"""Fleet Telemetry field name registry and preset configurations.

Field IDs sourced from Tesla's ``vehicle_data.proto`` Field enum.
Presets define commonly-used field groups with appropriate polling
intervals for different use cases.
"""

from __future__ import annotations

from tescmd.api.errors import ConfigError

# ---------------------------------------------------------------------------
# Field enum → human-readable name  (from vehicle_data.proto)
# ---------------------------------------------------------------------------

FIELD_NAMES: dict[int, str] = {
    1: "DriveState",
    2: "ChargeState",
    3: "Soc",
    4: "VehicleSpeed",
    5: "Odometer",
    6: "PackVoltage",
    7: "PackCurrent",
    8: "BatteryLevel",
    9: "Location",
    10: "Gear",
    11: "EstBatteryRange",
    12: "IdealBatteryRange",
    13: "RatedBatteryRange",
    14: "ACChargingEnergyIn",
    15: "ACChargingPower",
    16: "DCChargingEnergyIn",
    17: "DCChargingPower",
    18: "ChargeCurrentRequest",
    19: "ChargeCurrentRequestMax",
    20: "ChargeLimitSoc",
    21: "ChargePortDoorOpen",
    22: "ChargePortLatch",
    23: "ChargerActualCurrent",
    24: "ChargerPhases",
    25: "ChargerPilotCurrent",
    26: "ChargerVoltage",
    27: "FastChargerPresent",
    28: "ScheduledChargingMode",
    29: "ScheduledChargingPending",
    30: "ScheduledChargingStartTime",
    31: "ScheduledDepartureTime",
    32: "TimeToFullCharge",
    33: "InsideTemp",
    34: "OutsideTemp",
    35: "DriverTempSetting",
    36: "PassengerTempSetting",
    37: "IsClimateOn",
    38: "FanStatus",
    39: "LeftTempDirection",
    40: "RightTempDirection",
    41: "SeatHeaterLeft",
    42: "SeatHeaterRight",
    43: "SeatHeaterRearLeft",
    44: "SeatHeaterRearCenter",
    45: "SeatHeaterRearRight",
    46: "SteeringWheelHeater",
    47: "AutoSeatClimateLeft",
    48: "AutoSeatClimateRight",
    49: "CabinOverheatProtection",
    50: "DefrostMode",
    51: "Locked",
    52: "SentryMode",
    53: "CenterDisplay",
    54: "ValetMode",
    55: "RemoteStart",
    56: "DoorState",
    57: "WindowState",
    58: "TrunkOpen",
    59: "FrunkOpen",
    60: "SoftwareVersion",
    61: "TpmsPressureFl",
    62: "TpmsPressureFr",
    63: "TpmsPressureRl",
    64: "TpmsPressureRr",
    65: "DetailedChargeState",
    66: "HomeLink",
    67: "UserPresent",
    68: "DashcamState",
    69: "RearSeatHeaters",
    70: "BatteryHeaterOn",
    71: "NotEnoughPowerToHeat",
    72: "BmsFullchargecomplete",
    73: "ChargeEnablerequest",
    74: "ChargerPhases2",
    75: "EnergyRemaining",
    76: "LifetimeEnergyUsed",
    77: "LifetimeEnergyUsedDrive",
    78: "BMSState",
    79: "GuestModeEnabled",
    80: "PreconditioningEnabled",
    81: "ScheduledChargingStartTimeApp",
    82: "TripCharging",
    83: "ChargingCableType",
    84: "RouteLastUpdated",
    85: "RouteLine",
    86: "MilesToArrival",
    87: "MinutesToArrival",
    88: "TrafficMinutesDelay",
    89: "Elevation",
    90: "Heading",
    91: "PowerState",
    92: "RatedRange",
    93: "CruiseState",
    94: "CruiseSetSpeed",
    95: "LaneAssistLevel",
    96: "AutopilotState",
    97: "AutopilotHandsOnState",
    98: "SpeedLimitMode",
    99: "SpeedLimitWarning",
    100: "MaxSpeedLimit",
    101: "SunRoofPercentOpen",
    102: "SunRoofState",
    103: "TonneauPosition",
    104: "TonneauState",
    105: "WiperHeatEnabled",
    106: "BrakePedalPos",
    107: "PedalPosition",
    108: "DriveRailAmps12v",
    109: "BrickVoltageMax",
    110: "BrickVoltageMin",
    111: "ModuleTempMax",
    112: "ModuleTempMin",
    113: "NumBrickVoltageMax",
    114: "NumBrickVoltageMin",
    115: "NumModuleTempMax",
    116: "NumModuleTempMin",
    117: "ChargeAmps",
    118: "FastChargerType",
    119: "ConnChargeCable",
    120: "Supercharger",
}

# ---------------------------------------------------------------------------
# Preset field configurations
# ---------------------------------------------------------------------------

DEFAULT_FIELDS: dict[str, dict[str, int]] = {
    "Soc": {"interval_seconds": 10},
    "VehicleSpeed": {"interval_seconds": 1},
    "Location": {"interval_seconds": 5},
    "ChargeState": {"interval_seconds": 10},
    "InsideTemp": {"interval_seconds": 30},
    "OutsideTemp": {"interval_seconds": 60},
    "Odometer": {"interval_seconds": 60},
    "BatteryLevel": {"interval_seconds": 10},
    "Gear": {"interval_seconds": 1},
    "PackVoltage": {"interval_seconds": 10},
    "PackCurrent": {"interval_seconds": 10},
}

PRESETS: dict[str, dict[str, dict[str, int]]] = {
    "default": DEFAULT_FIELDS,
    "driving": {
        "VehicleSpeed": {"interval_seconds": 1},
        "Location": {"interval_seconds": 1},
        "Gear": {"interval_seconds": 1},
        "Heading": {"interval_seconds": 1},
        "Odometer": {"interval_seconds": 10},
        "Elevation": {"interval_seconds": 5},
        "BatteryLevel": {"interval_seconds": 10},
        "Soc": {"interval_seconds": 10},
        "PackCurrent": {"interval_seconds": 5},
        "PackVoltage": {"interval_seconds": 5},
        "CruiseState": {"interval_seconds": 5},
        "CruiseSetSpeed": {"interval_seconds": 5},
        "PowerState": {"interval_seconds": 10},
    },
    "charging": {
        "Soc": {"interval_seconds": 5},
        "BatteryLevel": {"interval_seconds": 5},
        "PackVoltage": {"interval_seconds": 5},
        "PackCurrent": {"interval_seconds": 5},
        "ChargeState": {"interval_seconds": 5},
        "ChargerActualCurrent": {"interval_seconds": 5},
        "ChargerVoltage": {"interval_seconds": 5},
        "ChargerPhases": {"interval_seconds": 30},
        "ACChargingPower": {"interval_seconds": 5},
        "DCChargingPower": {"interval_seconds": 5},
        "TimeToFullCharge": {"interval_seconds": 30},
        "ChargeLimitSoc": {"interval_seconds": 60},
        "ChargePortDoorOpen": {"interval_seconds": 60},
        "BatteryHeaterOn": {"interval_seconds": 30},
        "InsideTemp": {"interval_seconds": 60},
    },
    "climate": {
        "InsideTemp": {"interval_seconds": 10},
        "OutsideTemp": {"interval_seconds": 30},
        "DriverTempSetting": {"interval_seconds": 30},
        "PassengerTempSetting": {"interval_seconds": 30},
        "IsClimateOn": {"interval_seconds": 10},
        "FanStatus": {"interval_seconds": 10},
        "SeatHeaterLeft": {"interval_seconds": 30},
        "SeatHeaterRight": {"interval_seconds": 30},
        "SteeringWheelHeater": {"interval_seconds": 30},
        "CabinOverheatProtection": {"interval_seconds": 60},
        "DefrostMode": {"interval_seconds": 30},
        "PreconditioningEnabled": {"interval_seconds": 30},
    },
    "all": {name: {"interval_seconds": 30} for name in FIELD_NAMES.values()},
}

# Reverse lookup: name → ID
_NAME_TO_ID: dict[str, int] = {v: k for k, v in FIELD_NAMES.items()}


def resolve_fields(
    spec: str,
    interval_override: int | None = None,
) -> dict[str, dict[str, int]]:
    """Resolve a ``--fields`` argument to a field configuration dict.

    Args:
        spec: A preset name (e.g. ``"default"``, ``"charging"``) or a
            comma-separated list of field names (e.g. ``"Soc,VehicleSpeed"``).
        interval_override: If set, overrides ``interval_seconds`` for all fields.

    Returns:
        A dict mapping field names to ``{"interval_seconds": N}``.

    Raises:
        ConfigError: If a field name or preset is unrecognized.
    """
    if spec in PRESETS:
        fields = dict(PRESETS[spec])
    else:
        # Comma-separated field names
        fields = {}
        for name in spec.split(","):
            name = name.strip()
            if not name:
                continue
            if name not in _NAME_TO_ID:
                raise ConfigError(
                    f"Unknown telemetry field: '{name}'. "
                    f"Available presets: {', '.join(sorted(PRESETS.keys()))}"
                )
            fields[name] = {"interval_seconds": 10}  # reasonable default

    if interval_override is not None:
        fields = {name: {"interval_seconds": interval_override} for name in fields}

    return fields
