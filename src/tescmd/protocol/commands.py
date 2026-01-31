"""Command registry: maps REST command names to protocol domain + payload builders.

Each command has a domain (VCSEC, INFOTAINMENT, or UNSIGNED) and a builder
function that converts the JSON body dict into protobuf payload bytes.

For the Vehicle Command Protocol, the payload is either:
  - An Infotainment ``Action`` protobuf (for car-server commands)
  - A VCSEC ``UnsignedMessage`` protobuf (for security commands)
  - None for unsigned commands (wake_up)

Since we don't have full protobuf generation, the payload is currently
passed through as JSON-encoded bytes. The ``signed_command`` endpoint
accepts both protobuf and JSON payloads — the protobuf wrapping in
RoutableMessage is what matters for authentication.
"""

from __future__ import annotations

from dataclasses import dataclass

from tescmd.protocol.protobuf.messages import Domain


@dataclass(frozen=True)
class CommandSpec:
    """Specification for a vehicle command."""

    domain: Domain
    requires_signing: bool = True
    action_type: str = ""  # Protobuf action type identifier


# ---------------------------------------------------------------------------
# VCSEC commands (security domain)
# ---------------------------------------------------------------------------

_VCSEC_COMMANDS: dict[str, CommandSpec] = {
    "door_lock": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY, action_type="RKE_ACTION_LOCK"),
    "door_unlock": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY, action_type="RKE_ACTION_UNLOCK"),
    "actuate_trunk": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY),
    "window_control": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY),
    "open_tonneau": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY),
    "close_tonneau": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY),
    "stop_tonneau": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY),
    "remote_start_drive": CommandSpec(Domain.DOMAIN_VEHICLE_SECURITY),
    "flash_lights": CommandSpec(
        Domain.DOMAIN_VEHICLE_SECURITY, action_type="RKE_ACTION_REMOTE_DRIVE"
    ),
}

# ---------------------------------------------------------------------------
# Infotainment commands (car-server domain)
# ---------------------------------------------------------------------------

_INFOTAINMENT_COMMANDS: dict[str, CommandSpec] = {
    # Charging
    "charge_start": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "charge_stop": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "charge_standard": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "charge_max_range": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "charge_port_door_open": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "charge_port_door_close": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_charge_limit": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_charging_amps": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_scheduled_charging": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_scheduled_departure": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "add_precondition_schedule": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remove_precondition_schedule": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "add_charge_schedule": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remove_charge_schedule": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Climate
    "auto_conditioning_start": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "auto_conditioning_stop": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_temps": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_preconditioning_max": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remote_seat_heater_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remote_seat_cooler_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remote_steering_wheel_heater_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_cabin_overheat_protection": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_climate_keeper_mode": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_cop_temp": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remote_auto_seat_climate_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remote_auto_steering_wheel_heat_climate_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remote_steering_wheel_heat_level_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_bioweapon_mode": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Security (infotainment-routed)
    "set_sentry_mode": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_valet_mode": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "reset_valet_pin": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "speed_limit_activate": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "speed_limit_deactivate": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "speed_limit_set_limit": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "speed_limit_clear_pin": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "reset_pin_to_drive_pin": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "clear_pin_to_drive_admin": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "speed_limit_clear_pin_admin": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "honk_horn": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "set_pin_to_drive": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "guest_mode": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "erase_user_data": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "remote_boombox": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Media
    "media_toggle_playback": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "media_next_track": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "media_prev_track": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "media_next_fav": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "media_prev_fav": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "media_volume_up": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "media_volume_down": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "adjust_volume": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Navigation
    "share": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "navigation_gps_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "navigation_sc_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "trigger_homelink": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "navigation_waypoints_request": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Software
    "schedule_software_update": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "cancel_software_update": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Vehicle name / calendar
    "set_vehicle_name": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "upcoming_calendar_entries": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Sunroof
    "sun_roof_control": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    # Power management
    "set_low_power_mode": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
    "keep_accessory_power_mode": CommandSpec(Domain.DOMAIN_INFOTAINMENT),
}

# ---------------------------------------------------------------------------
# Unsigned commands (no signing required)
# ---------------------------------------------------------------------------

_UNSIGNED_COMMANDS: dict[str, CommandSpec] = {
    "wake_up": CommandSpec(Domain.DOMAIN_BROADCAST, requires_signing=False),
    "set_managed_charge_current_request": CommandSpec(
        Domain.DOMAIN_BROADCAST, requires_signing=False
    ),
}

# ---------------------------------------------------------------------------
# Unified registry
# ---------------------------------------------------------------------------

COMMAND_REGISTRY: dict[str, CommandSpec] = {
    **_VCSEC_COMMANDS,
    **_INFOTAINMENT_COMMANDS,
    **_UNSIGNED_COMMANDS,
}


def get_command_spec(command: str) -> CommandSpec | None:
    """Look up a command specification by REST command name."""
    return COMMAND_REGISTRY.get(command)


def get_domain(command: str) -> Domain | None:
    """Return the domain for a command, or None if unknown."""
    spec = COMMAND_REGISTRY.get(command)
    return spec.domain if spec else None


def requires_signing(command: str) -> bool:
    """Return True if the command requires a signed channel."""
    spec = COMMAND_REGISTRY.get(command)
    if spec is None:
        return False  # Unknown commands fall through to unsigned path
    return spec.requires_signing
