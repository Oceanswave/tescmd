"""Fleet Telemetry field name registry and preset configurations.

Field IDs and names sourced from Tesla's ``vehicle_data.proto`` Field enum
(https://github.com/teslamotors/fleet-telemetry/blob/main/protos/vehicle_data.proto).

Presets define commonly-used field groups with appropriate polling
intervals for different use cases.
"""

from __future__ import annotations

from tescmd.api.errors import ConfigError

# ---------------------------------------------------------------------------
# Field enum → human-readable name  (from vehicle_data.proto)
#
# IDs and names match the proto exactly.  Excluded:
#   - Unknown (0)
#   - Deprecated_1 (162), Deprecated_2 (100), Deprecated_3 (257)
#   - Experimental_1-15 (119-122, 168-178)
# ---------------------------------------------------------------------------

FIELD_NAMES: dict[int, str] = {
    # --- Drive / Motion ---
    1: "DriveRail",
    4: "VehicleSpeed",
    5: "Odometer",
    10: "Gear",
    12: "PedalPosition",
    13: "BrakePedal",
    21: "Location",
    22: "GpsState",
    23: "GpsHeading",
    98: "LateralAcceleration",
    99: "LongitudinalAcceleration",
    101: "CruiseSetSpeed",
    106: "BrakePedalPos",
    126: "CruiseFollowDistance",
    129: "SpeedLimitWarning",
    # --- Battery / Energy ---
    6: "PackVoltage",
    7: "PackCurrent",
    8: "Soc",
    9: "DCDCEnable",
    11: "IsolationResistance",
    24: "NumBrickVoltageMax",
    25: "BrickVoltageMax",
    26: "NumBrickVoltageMin",
    27: "BrickVoltageMin",
    28: "NumModuleTempMax",
    29: "ModuleTempMax",
    30: "NumModuleTempMin",
    31: "ModuleTempMin",
    32: "RatedRange",
    33: "Hvil",
    40: "EstBatteryRange",
    41: "IdealBatteryRange",
    42: "BatteryLevel",
    55: "BatteryHeaterOn",
    56: "NotEnoughPowerToHeat",
    102: "LifetimeEnergyUsed",
    103: "LifetimeEnergyUsedDrive",
    134: "LifetimeEnergyGainedRegen",
    158: "EnergyRemaining",
    160: "BMSState",
    # --- Charging ---
    2: "ChargeState",
    3: "BmsFullchargecomplete",
    34: "DCChargingEnergyIn",
    35: "DCChargingPower",
    36: "ACChargingEnergyIn",
    37: "ACChargingPower",
    38: "ChargeLimitSoc",
    39: "FastChargerPresent",
    43: "TimeToFullCharge",
    44: "ScheduledChargingStartTime",
    45: "ScheduledChargingPending",
    46: "ScheduledDepartureTime",
    47: "PreconditioningEnabled",
    48: "ScheduledChargingMode",
    49: "ChargeAmps",
    50: "ChargeEnableRequest",
    51: "ChargerPhases",
    52: "ChargePortColdWeatherMode",
    53: "ChargeCurrentRequest",
    54: "ChargeCurrentRequestMax",
    57: "SuperchargerSessionTripPlanner",
    117: "ChargePort",
    118: "ChargePortLatch",
    179: "DetailedChargeState",
    183: "ChargePortDoorOpen",
    184: "ChargerVoltage",
    185: "ChargingCableType",
    190: "EstimatedHoursToChargeTermination",
    193: "FastChargerType",
    256: "ChargeRateMilePerHour",
    # --- Climate / HVAC ---
    85: "InsideTemp",
    86: "OutsideTemp",
    87: "SeatHeaterLeft",
    88: "SeatHeaterRight",
    89: "SeatHeaterRearLeft",
    90: "SeatHeaterRearRight",
    91: "SeatHeaterRearCenter",
    92: "AutoSeatClimateLeft",
    93: "AutoSeatClimateRight",
    186: "ClimateKeeperMode",
    187: "DefrostForPreconditioning",
    188: "DefrostMode",
    196: "HvacACEnabled",
    197: "HvacAutoMode",
    198: "HvacFanSpeed",
    199: "HvacFanStatus",
    200: "HvacLeftTemperatureRequest",
    201: "HvacPower",
    202: "HvacRightTemperatureRequest",
    203: "HvacSteeringWheelHeatAuto",
    204: "HvacSteeringWheelHeatLevel",
    211: "RearDisplayHvacEnabled",
    237: "ClimateSeatCoolingFrontLeft",
    238: "ClimateSeatCoolingFrontRight",
    254: "SeatVentEnabled",
    255: "RearDefrostEnabled",
    180: "CabinOverheatProtectionMode",
    181: "CabinOverheatProtectionTemperatureLimit",
    # --- Security / Doors / Windows ---
    58: "DoorState",
    59: "Locked",
    60: "FdWindow",
    61: "FpWindow",
    62: "RdWindow",
    63: "RpWindow",
    64: "VehicleName",
    65: "SentryMode",
    66: "SpeedLimitMode",
    67: "CurrentLimitMph",
    68: "Version",
    94: "DriverSeatBelt",
    95: "PassengerSeatBelt",
    96: "DriverSeatOccupied",
    123: "GuestModeEnabled",
    124: "PinToDriveEnabled",
    125: "PairedPhoneKeyAndKeyFobQty",
    159: "ServiceMode",
    161: "GuestModeMobileAccessState",
    182: "CenterDisplay",
    213: "RemoteStartEnabled",
    226: "ValetModeEnabled",
    # --- Tires ---
    69: "TpmsPressureFl",
    70: "TpmsPressureFr",
    71: "TpmsPressureRl",
    72: "TpmsPressureRr",
    81: "TpmsLastSeenPressureTimeFl",
    82: "TpmsLastSeenPressureTimeFr",
    83: "TpmsLastSeenPressureTimeRl",
    84: "TpmsLastSeenPressureTimeRr",
    224: "TpmsHardWarnings",
    225: "TpmsSoftWarnings",
    # --- Drive Inverter (per-motor diagnostics) ---
    14: "DiStateR",
    15: "DiHeatsinkTR",
    16: "DiAxleSpeedR",
    17: "DiTorquemotor",
    18: "DiStatorTempR",
    19: "DiVBatR",
    20: "DiMotorCurrentR",
    135: "DiStateF",
    136: "DiStateREL",
    137: "DiStateRER",
    138: "DiHeatsinkTF",
    139: "DiHeatsinkTREL",
    140: "DiHeatsinkTRER",
    141: "DiAxleSpeedF",
    142: "DiAxleSpeedREL",
    143: "DiAxleSpeedRER",
    144: "DiSlaveTorqueCmd",
    145: "DiTorqueActualR",
    146: "DiTorqueActualF",
    147: "DiTorqueActualREL",
    148: "DiTorqueActualRER",
    149: "DiStatorTempF",
    150: "DiStatorTempREL",
    151: "DiStatorTempRER",
    152: "DiVBatF",
    153: "DiVBatREL",
    154: "DiVBatRER",
    155: "DiMotorCurrentF",
    156: "DiMotorCurrentREL",
    157: "DiMotorCurrentRER",
    164: "DiInverterTR",
    165: "DiInverterTF",
    166: "DiInverterTREL",
    167: "DiInverterTRER",
    # --- Navigation / Route ---
    107: "RouteLastUpdated",
    108: "RouteLine",
    109: "MilesToArrival",
    110: "MinutesToArrival",
    111: "OriginLocation",
    112: "DestinationLocation",
    163: "DestinationName",
    215: "RouteTrafficMinutesDelay",
    192: "ExpectedEnergyPercentAtTripArrival",
    # --- Vehicle Info / Config ---
    113: "CarType",
    114: "Trim",
    115: "ExteriorColor",
    116: "RoofColor",
    189: "EfficiencyPackage",
    191: "EuropeVehicle",
    214: "RightHandDrive",
    227: "WheelType",
    228: "WiperHeatEnabled",
    # --- Safety / ADAS ---
    127: "AutomaticBlindSpotCamera",
    128: "BlindSpotCollisionWarningChime",
    130: "ForwardCollisionWarning",
    131: "LaneDepartureAvoidance",
    132: "EmergencyLaneDepartureAvoidance",
    133: "AutomaticEmergencyBrakingOff",
    # --- Powershare ---
    206: "PowershareHoursLeft",
    207: "PowershareInstantaneousPowerKW",
    208: "PowershareStatus",
    209: "PowershareStopReason",
    210: "PowershareType",
    # --- Homelink ---
    194: "HomelinkDeviceCount",
    195: "HomelinkNearby",
    # --- Software Updates ---
    216: "SoftwareUpdateDownloadPercentComplete",
    217: "SoftwareUpdateExpectedDurationMinutes",
    218: "SoftwareUpdateInstallationPercentComplete",
    219: "SoftwareUpdateScheduledStartTime",
    220: "SoftwareUpdateVersion",
    # --- Tonneau ---
    221: "TonneauOpenPercent",
    222: "TonneauPosition",
    223: "TonneauTentMode",
    # --- Location Context ---
    229: "LocatedAtHome",
    230: "LocatedAtWork",
    231: "LocatedAtFavorite",
    # --- Settings ---
    232: "SettingDistanceUnit",
    233: "SettingTemperatureUnit",
    234: "Setting24HourTime",
    235: "SettingTirePressureUnit",
    236: "SettingChargeUnit",
    # --- Lights ---
    239: "LightsHazardsActive",
    240: "LightsTurnSignal",
    241: "LightsHighBeams",
    # --- Media ---
    242: "MediaPlaybackStatus",
    243: "MediaPlaybackSource",
    244: "MediaAudioVolume",
    245: "MediaNowPlayingDuration",
    246: "MediaNowPlayingElapsed",
    247: "MediaNowPlayingArtist",
    248: "MediaNowPlayingTitle",
    249: "MediaNowPlayingAlbum",
    250: "MediaNowPlayingStation",
    251: "MediaAudioVolumeIncrement",
    252: "MediaAudioVolumeMax",
    # --- Misc ---
    205: "OffroadLightbarPresent",
    212: "RearSeatHeaters",
    253: "SunroofInstalled",
    258: "MilesSinceReset",
    259: "SelfDrivingMilesSinceReset",
    # --- Semi-truck (included for completeness, excluded from presets) ---
    73: "SemitruckTpmsPressureRe1L0",
    74: "SemitruckTpmsPressureRe1L1",
    75: "SemitruckTpmsPressureRe1R0",
    76: "SemitruckTpmsPressureRe1R1",
    77: "SemitruckTpmsPressureRe2L0",
    78: "SemitruckTpmsPressureRe2L1",
    79: "SemitruckTpmsPressureRe2R0",
    80: "SemitruckTpmsPressureRe2R1",
    97: "SemitruckPassengerSeatFoldPosition",
    104: "SemitruckTractorParkBrakeStatus",
    105: "SemitruckTrailerParkBrakeStatus",
}

# ---------------------------------------------------------------------------
# Fields that exist in vehicle_data.proto but should be excluded from the
# "all" preset.  Semi-truck fields won't work on consumer vehicles.
# LifetimeEnergyGainedRegen returns "unsupported_field" on many vehicles.
# ---------------------------------------------------------------------------

_NON_STREAMABLE_FIELDS: frozenset[str] = frozenset(
    {name for name in FIELD_NAMES.values() if name.startswith("Semitruck")}
    | {
        "LifetimeEnergyGainedRegen",  # returns "unsupported_field" on many vehicles
        # These require minimum_delta config instead of interval_seconds:
        "MilesSinceReset",
        "SelfDrivingMilesSinceReset",
    }
)

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
        "GpsHeading": {"interval_seconds": 1},
        "Odometer": {"interval_seconds": 10},
        "BatteryLevel": {"interval_seconds": 10},
        "Soc": {"interval_seconds": 10},
        "PackCurrent": {"interval_seconds": 5},
        "PackVoltage": {"interval_seconds": 5},
        "CruiseSetSpeed": {"interval_seconds": 5},
        "LateralAcceleration": {"interval_seconds": 5},
        "LongitudinalAcceleration": {"interval_seconds": 5},
        "BrakePedalPos": {"interval_seconds": 5},
        "PedalPosition": {"interval_seconds": 5},
    },
    "charging": {
        "Soc": {"interval_seconds": 5},
        "BatteryLevel": {"interval_seconds": 5},
        "PackVoltage": {"interval_seconds": 5},
        "PackCurrent": {"interval_seconds": 5},
        "ChargeState": {"interval_seconds": 5},
        "ChargeAmps": {"interval_seconds": 5},
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
        "HvacLeftTemperatureRequest": {"interval_seconds": 30},
        "HvacRightTemperatureRequest": {"interval_seconds": 30},
        "HvacPower": {"interval_seconds": 10},
        "HvacFanStatus": {"interval_seconds": 10},
        "SeatHeaterLeft": {"interval_seconds": 30},
        "SeatHeaterRight": {"interval_seconds": 30},
        "HvacSteeringWheelHeatLevel": {"interval_seconds": 30},
        "CabinOverheatProtectionMode": {"interval_seconds": 60},
        "DefrostMode": {"interval_seconds": 30},
        "PreconditioningEnabled": {"interval_seconds": 30},
    },
    "all": {
        name: {"interval_seconds": 30}
        for name in FIELD_NAMES.values()
        if name not in _NON_STREAMABLE_FIELDS
    },
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
