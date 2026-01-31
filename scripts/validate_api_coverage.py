#!/usr/bin/env python3
"""Validate tescmd API coverage against the Tesla Fleet API specification.

Cross-references:
  - Tesla Fleet API REST documentation (66+ vehicle command endpoints)
  - Tesla Go SDK pkg/proxy/command.go (authoritative REST body param names)
  - Tesla Fleet API vehicle, energy, charging, user, partner endpoints

Usage:
    python scripts/validate_api_coverage.py
"""

from __future__ import annotations

import ast
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Spec: Tesla Fleet API ground truth (Go SDK ExtractCommandAction + REST docs)
# ---------------------------------------------------------------------------


@dataclass
class ParamSpec:
    name: str
    type: str  # "bool", "int", "float", "str", "dict", "Any"
    required: bool = True
    default: Any = None


@dataclass
class EndpointSpec:
    """One Tesla Fleet API endpoint."""

    name: str
    method: str  # "POST" or "GET"
    path: str
    params: list[ParamSpec] = field(default_factory=list)
    domain: str = ""  # "vcsec", "infotainment", "unsigned", "rest_only"
    notes: str = ""


# fmt: off

# === VEHICLE COMMANDS (POST /api/1/vehicles/{vin}/command/{name}) ===
# Parameter names/types from Go SDK ExtractCommandAction (authoritative)

VEHICLE_COMMANDS: list[EndpointSpec] = [
    # -- Charging --
    EndpointSpec("charge_start", "POST", "/command/charge_start", domain="infotainment"),
    EndpointSpec("charge_stop", "POST", "/command/charge_stop", domain="infotainment"),
    EndpointSpec("charge_standard", "POST", "/command/charge_standard", domain="infotainment"),
    EndpointSpec("charge_max_range", "POST", "/command/charge_max_range", domain="infotainment"),
    EndpointSpec("charge_port_door_open", "POST", "/command/charge_port_door_open", domain="infotainment"),
    EndpointSpec("charge_port_door_close", "POST", "/command/charge_port_door_close", domain="infotainment"),
    EndpointSpec("set_charge_limit", "POST", "/command/set_charge_limit",
                 [ParamSpec("percent", "int")], domain="infotainment"),
    EndpointSpec("set_charging_amps", "POST", "/command/set_charging_amps",
                 [ParamSpec("charging_amps", "int")], domain="infotainment"),
    EndpointSpec("set_scheduled_charging", "POST", "/command/set_scheduled_charging",
                 [ParamSpec("enable", "bool"), ParamSpec("time", "int", required=False)],
                 domain="infotainment"),
    EndpointSpec("set_scheduled_departure", "POST", "/command/set_scheduled_departure",
                 [ParamSpec("enable", "bool"),
                  ParamSpec("departure_time", "int", required=False),
                  ParamSpec("preconditioning_enabled", "bool", required=False),
                  ParamSpec("preconditioning_weekdays_only", "bool", required=False),
                  ParamSpec("off_peak_charging_enabled", "bool", required=False),
                  ParamSpec("off_peak_charging_weekdays_only", "bool", required=False),
                  ParamSpec("end_off_peak_time", "int", required=False)],
                 domain="infotainment"),
    EndpointSpec("add_charge_schedule", "POST", "/command/add_charge_schedule",
                 [ParamSpec("schedule", "dict")], domain="infotainment",
                 notes="Go SDK has specific fields; we pass dict through"),
    EndpointSpec("remove_charge_schedule", "POST", "/command/remove_charge_schedule",
                 [ParamSpec("id", "int")], domain="infotainment"),
    EndpointSpec("add_precondition_schedule", "POST", "/command/add_precondition_schedule",
                 [ParamSpec("schedule", "dict")], domain="infotainment",
                 notes="Go SDK has specific fields; we pass dict through"),
    EndpointSpec("remove_precondition_schedule", "POST", "/command/remove_precondition_schedule",
                 [ParamSpec("id", "int")], domain="infotainment"),

    # -- Climate --
    EndpointSpec("auto_conditioning_start", "POST", "/command/auto_conditioning_start",
                 domain="infotainment"),
    EndpointSpec("auto_conditioning_stop", "POST", "/command/auto_conditioning_stop",
                 domain="infotainment"),
    EndpointSpec("set_temps", "POST", "/command/set_temps",
                 [ParamSpec("driver_temp", "float", required=False),
                  ParamSpec("passenger_temp", "float", required=False)],
                 domain="infotainment"),
    EndpointSpec("set_preconditioning_max", "POST", "/command/set_preconditioning_max",
                 [ParamSpec("on", "bool"),
                  ParamSpec("manual_override", "bool", required=False)],
                 domain="infotainment"),
    EndpointSpec("remote_seat_heater_request", "POST", "/command/remote_seat_heater_request",
                 [ParamSpec("seat_position", "int"), ParamSpec("level", "int")],
                 domain="infotainment",
                 notes="Go SDK uses 'seat_position' not 'heater'"),
    EndpointSpec("remote_seat_cooler_request", "POST", "/command/remote_seat_cooler_request",
                 [ParamSpec("seat_position", "int"), ParamSpec("seat_cooler_level", "int")],
                 domain="infotainment"),
    EndpointSpec("remote_steering_wheel_heater_request", "POST",
                 "/command/remote_steering_wheel_heater_request",
                 [ParamSpec("on", "bool")], domain="infotainment"),
    EndpointSpec("set_cabin_overheat_protection", "POST",
                 "/command/set_cabin_overheat_protection",
                 [ParamSpec("on", "bool"),
                  ParamSpec("fan_only", "bool", required=False)],
                 domain="infotainment"),
    EndpointSpec("set_climate_keeper_mode", "POST", "/command/set_climate_keeper_mode",
                 [ParamSpec("climate_keeper_mode", "int"),
                  ParamSpec("manual_override", "bool", required=False)],
                 domain="infotainment"),
    EndpointSpec("set_cop_temp", "POST", "/command/set_cop_temp",
                 [ParamSpec("cop_temp", "int")], domain="infotainment",
                 notes="Go SDK Level type maps to int (0/1/2)"),
    EndpointSpec("remote_auto_seat_climate_request", "POST",
                 "/command/remote_auto_seat_climate_request",
                 [ParamSpec("auto_seat_position", "int"),
                  ParamSpec("auto_climate_on", "bool")],
                 domain="infotainment",
                 notes="Go SDK uses 'auto_climate_on' not 'on'"),
    EndpointSpec("remote_auto_steering_wheel_heat_climate_request", "POST",
                 "/command/remote_auto_steering_wheel_heat_climate_request",
                 [ParamSpec("on", "bool")], domain="infotainment",
                 notes="Not in Go SDK ExtractCommandAction; REST-only or newer"),
    EndpointSpec("remote_steering_wheel_heat_level_request", "POST",
                 "/command/remote_steering_wheel_heat_level_request",
                 [ParamSpec("level", "int")], domain="infotainment",
                 notes="Not in Go SDK ExtractCommandAction; REST-only or newer"),
    EndpointSpec("set_bioweapon_mode", "POST", "/command/set_bioweapon_mode",
                 [ParamSpec("on", "bool"),
                  ParamSpec("manual_override", "bool", required=False)],
                 domain="infotainment"),

    # -- Security --
    EndpointSpec("door_lock", "POST", "/command/door_lock", domain="vcsec"),
    EndpointSpec("door_unlock", "POST", "/command/door_unlock", domain="vcsec"),
    EndpointSpec("set_sentry_mode", "POST", "/command/set_sentry_mode",
                 [ParamSpec("on", "bool")], domain="infotainment"),
    EndpointSpec("set_valet_mode", "POST", "/command/set_valet_mode",
                 [ParamSpec("on", "bool"),
                  ParamSpec("password", "str", required=False)],
                 domain="infotainment"),
    EndpointSpec("reset_valet_pin", "POST", "/command/reset_valet_pin",
                 domain="infotainment"),
    EndpointSpec("speed_limit_activate", "POST", "/command/speed_limit_activate",
                 [ParamSpec("pin", "str")], domain="infotainment"),
    EndpointSpec("speed_limit_deactivate", "POST", "/command/speed_limit_deactivate",
                 [ParamSpec("pin", "str")], domain="infotainment"),
    EndpointSpec("speed_limit_set_limit", "POST", "/command/speed_limit_set_limit",
                 [ParamSpec("limit_mph", "float")], domain="infotainment",
                 notes="Go SDK uses float64"),
    EndpointSpec("speed_limit_clear_pin", "POST", "/command/speed_limit_clear_pin",
                 [ParamSpec("pin", "str")], domain="infotainment"),
    EndpointSpec("speed_limit_clear_pin_admin", "POST",
                 "/command/speed_limit_clear_pin_admin", domain="infotainment"),
    EndpointSpec("reset_pin_to_drive_pin", "POST", "/command/reset_pin_to_drive_pin",
                 domain="infotainment"),
    EndpointSpec("clear_pin_to_drive_admin", "POST", "/command/clear_pin_to_drive_admin",
                 domain="infotainment"),
    EndpointSpec("remote_start_drive", "POST", "/command/remote_start_drive",
                 domain="vcsec"),
    EndpointSpec("flash_lights", "POST", "/command/flash_lights", domain="vcsec"),
    EndpointSpec("honk_horn", "POST", "/command/honk_horn", domain="infotainment"),
    EndpointSpec("set_pin_to_drive", "POST", "/command/set_pin_to_drive",
                 [ParamSpec("on", "bool"),
                  ParamSpec("password", "str", required=False)],
                 domain="infotainment"),
    EndpointSpec("guest_mode", "POST", "/command/guest_mode",
                 [ParamSpec("enable", "bool")], domain="infotainment"),
    EndpointSpec("erase_user_data", "POST", "/command/erase_user_data",
                 domain="infotainment"),
    EndpointSpec("remote_boombox", "POST", "/command/remote_boombox",
                 [ParamSpec("sound", "int", required=False)],
                 domain="rest_only",
                 notes="Go SDK: Not Implemented; REST-only with sound param"),

    # -- Media --
    EndpointSpec("media_toggle_playback", "POST", "/command/media_toggle_playback",
                 domain="infotainment"),
    EndpointSpec("media_next_track", "POST", "/command/media_next_track",
                 domain="infotainment"),
    EndpointSpec("media_prev_track", "POST", "/command/media_prev_track",
                 domain="infotainment"),
    EndpointSpec("media_next_fav", "POST", "/command/media_next_fav",
                 domain="infotainment"),
    EndpointSpec("media_prev_fav", "POST", "/command/media_prev_fav",
                 domain="infotainment"),
    EndpointSpec("media_volume_up", "POST", "/command/media_volume_up",
                 domain="infotainment"),
    EndpointSpec("media_volume_down", "POST", "/command/media_volume_down",
                 domain="infotainment"),
    EndpointSpec("adjust_volume", "POST", "/command/adjust_volume",
                 [ParamSpec("volume", "float")], domain="infotainment",
                 notes="Go SDK uses float32"),

    # -- Navigation --
    EndpointSpec("share", "POST", "/command/share",
                 [ParamSpec("address", "str")], domain="infotainment",
                 notes="Custom body format with share_ext_content_raw"),
    EndpointSpec("navigation_gps_request", "POST", "/command/navigation_gps_request",
                 [ParamSpec("lat", "float"), ParamSpec("lon", "float"),
                  ParamSpec("order", "int", required=False)],
                 domain="infotainment"),
    EndpointSpec("navigation_sc_request", "POST", "/command/navigation_sc_request",
                 domain="infotainment"),
    EndpointSpec("trigger_homelink", "POST", "/command/trigger_homelink",
                 [ParamSpec("lat", "float"), ParamSpec("lon", "float")],
                 domain="infotainment"),
    EndpointSpec("navigation_waypoints_request", "POST",
                 "/command/navigation_waypoints_request",
                 [ParamSpec("waypoints", "str")], domain="infotainment"),
    EndpointSpec("navigation_request", "POST", "/command/navigation_request",
                 [ParamSpec("type", "str"), ParamSpec("locale", "str"),
                  ParamSpec("timestamp_ms", "str"), ParamSpec("value", "dict")],
                 domain="rest_only",
                 notes="REST-only; deprecated in favor of 'share'"),

    # -- Software --
    EndpointSpec("schedule_software_update", "POST", "/command/schedule_software_update",
                 [ParamSpec("offset_sec", "int")], domain="infotainment"),
    EndpointSpec("cancel_software_update", "POST", "/command/cancel_software_update",
                 domain="infotainment"),

    # -- Trunk / windows --
    EndpointSpec("actuate_trunk", "POST", "/command/actuate_trunk",
                 [ParamSpec("which_trunk", "str")], domain="vcsec"),
    EndpointSpec("window_control", "POST", "/command/window_control",
                 [ParamSpec("command", "str"),
                  ParamSpec("lat", "float", required=False),
                  ParamSpec("lon", "float", required=False)],
                 domain="vcsec",
                 notes="Go SDK signed path only needs 'command'; REST needs lat/lon"),
    EndpointSpec("sun_roof_control", "POST", "/command/sun_roof_control",
                 [ParamSpec("state", "str")], domain="infotainment",
                 notes="state: vent, close, stop"),

    # -- Tonneau (Cybertruck) --
    EndpointSpec("open_tonneau", "POST", "/command/open_tonneau", domain="vcsec"),
    EndpointSpec("close_tonneau", "POST", "/command/close_tonneau", domain="vcsec"),
    EndpointSpec("stop_tonneau", "POST", "/command/stop_tonneau", domain="vcsec"),

    # -- Power management --
    EndpointSpec("set_low_power_mode", "POST", "/command/set_low_power_mode",
                 [ParamSpec("enable", "bool")], domain="infotainment",
                 notes="Go SDK uses 'enable' not 'on'"),
    EndpointSpec("keep_accessory_power_mode", "POST",
                 "/command/keep_accessory_power_mode",
                 [ParamSpec("enable", "bool")], domain="infotainment",
                 notes="Go SDK uses 'enable' not 'on'"),

    # -- Managed charging (fleet) --
    EndpointSpec("set_managed_charge_current_request", "POST",
                 "/command/set_managed_charge_current_request",
                 [ParamSpec("charging_amps", "int")], domain="unsigned",
                 notes="REST-only / unsigned"),
    EndpointSpec("set_managed_charger_location", "POST",
                 "/command/set_managed_charger_location",
                 [ParamSpec("location", "dict")], domain="rest_only",
                 notes="Fleet management; REST-only"),
    EndpointSpec("set_managed_scheduled_charging_time", "POST",
                 "/command/set_managed_scheduled_charging_time",
                 [ParamSpec("time", "int")], domain="rest_only",
                 notes="Fleet management; REST-only"),

    # -- Vehicle name / calendar --
    EndpointSpec("set_vehicle_name", "POST", "/command/set_vehicle_name",
                 [ParamSpec("vehicle_name", "str")], domain="infotainment"),
    EndpointSpec("upcoming_calendar_entries", "POST",
                 "/command/upcoming_calendar_entries",
                 [ParamSpec("calendar_data", "str")], domain="infotainment"),

    # -- Wake --
    EndpointSpec("wake_up", "POST", "/wake_up", domain="unsigned",
                 notes="Handled via VehicleAPI.wake(), not CommandAPI"),
]

# === VEHICLE DATA ENDPOINTS (GET) ===

VEHICLE_ENDPOINTS: list[EndpointSpec] = [
    EndpointSpec("list_vehicles", "GET", "/api/1/vehicles"),
    EndpointSpec("get_vehicle", "GET", "/api/1/vehicles/{vin}"),
    EndpointSpec("get_vehicle_data", "GET", "/api/1/vehicles/{vin}/vehicle_data",
                 [ParamSpec("endpoints", "str", required=False)]),
    EndpointSpec("wake", "POST", "/api/1/vehicles/{vin}/wake_up"),
    EndpointSpec("mobile_enabled", "GET", "/api/1/vehicles/{vin}/mobile_enabled"),
    EndpointSpec("nearby_charging_sites", "GET",
                 "/api/1/vehicles/{vin}/nearby_charging_sites"),
    EndpointSpec("recent_alerts", "GET", "/api/1/vehicles/{vin}/recent_alerts"),
    EndpointSpec("release_notes", "GET", "/api/1/vehicles/{vin}/release_notes"),
    EndpointSpec("service_data", "GET", "/api/1/vehicles/{vin}/service_data"),
    EndpointSpec("list_drivers", "GET", "/api/1/vehicles/{vin}/drivers"),
    # Missing from our impl:
    EndpointSpec("eligible_subscriptions", "GET",
                 "/api/1/dx/vehicles/subscriptions/eligibility",
                 [ParamSpec("vin", "str")]),
    EndpointSpec("eligible_upgrades", "GET",
                 "/api/1/dx/vehicles/upgrades/eligibility",
                 [ParamSpec("vin", "str")]),
    EndpointSpec("options", "GET", "/api/1/dx/vehicles/options",
                 [ParamSpec("vin", "str")]),
    EndpointSpec("specs", "GET", "/api/1/vehicles/{vin}/specs"),
    EndpointSpec("warranty_details", "GET", "/api/1/dx/warranty/details"),
    EndpointSpec("fleet_status", "POST", "/api/1/vehicles/fleet_status",
                 notes="Fleet management"),
    EndpointSpec("fleet_telemetry_config", "GET",
                 "/api/1/vehicles/{vin}/fleet_telemetry_config",
                 notes="Fleet/partner management"),
    EndpointSpec("fleet_telemetry_errors", "GET",
                 "/api/1/vehicles/{vin}/fleet_telemetry_errors",
                 notes="Fleet/partner management"),
    EndpointSpec("enterprise_roles", "GET",
                 "/api/1/dx/enterprise/v1/{vin}/roles",
                 notes="Enterprise/fleet management"),
    EndpointSpec("share_invites", "GET", "/api/1/vehicles/{vin}/invitations",
                 notes="Handled via SharingAPI"),
]

# === ENERGY ENDPOINTS ===

ENERGY_ENDPOINTS: list[EndpointSpec] = [
    EndpointSpec("list_products", "GET", "/api/1/products"),
    EndpointSpec("live_status", "GET",
                 "/api/1/energy_sites/{site_id}/live_status"),
    EndpointSpec("site_info", "GET",
                 "/api/1/energy_sites/{site_id}/site_info"),
    EndpointSpec("set_backup_reserve", "POST",
                 "/api/1/energy_sites/{site_id}/backup",
                 [ParamSpec("backup_reserve_percent", "int")]),
    EndpointSpec("set_operation_mode", "POST",
                 "/api/1/energy_sites/{site_id}/operation",
                 [ParamSpec("default_real_mode", "str")]),
    EndpointSpec("set_storm_mode", "POST",
                 "/api/1/energy_sites/{site_id}/storm_mode",
                 [ParamSpec("enabled", "bool")]),
    EndpointSpec("time_of_use_settings", "POST",
                 "/api/1/energy_sites/{site_id}/time_of_use_settings",
                 [ParamSpec("tou_settings", "dict")]),
    EndpointSpec("calendar_history", "GET",
                 "/api/1/energy_sites/{site_id}/calendar_history",
                 [ParamSpec("kind", "str"), ParamSpec("period", "str"),
                  ParamSpec("start_date", "str", required=False),
                  ParamSpec("end_date", "str", required=False)]),
    EndpointSpec("charging_history", "GET",
                 "/api/1/energy_sites/{site_id}/history",
                 notes="kind=charging variant"),
    EndpointSpec("off_grid_vehicle_charging_reserve", "POST",
                 "/api/1/energy_sites/{site_id}/off_grid_vehicle_charging_reserve",
                 [ParamSpec("off_grid_vehicle_charging_reserve_percent", "int")]),
    EndpointSpec("grid_import_export", "POST",
                 "/api/1/energy_sites/{site_id}/grid_import_export",
                 [ParamSpec("config", "dict")]),
    # Missing:
    EndpointSpec("telemetry_history", "GET",
                 "/api/1/energy_sites/{site_id}/telemetry_history",
                 notes="charge_history endpoint; not yet implemented"),
]

# === CHARGING ENDPOINTS ===

CHARGING_ENDPOINTS: list[EndpointSpec] = [
    EndpointSpec("charging_history", "GET", "/api/1/dx/charging/history",
                 notes="Supercharger charging history; not yet implemented"),
    EndpointSpec("charging_invoice", "GET", "/api/1/dx/charging/invoice/{id}",
                 [ParamSpec("id", "str")],
                 notes="Charging invoice; not yet implemented"),
    EndpointSpec("charging_sessions", "GET", "/api/1/dx/charging/sessions",
                 notes="Business fleet only; not yet implemented"),
]

# === USER ENDPOINTS ===

USER_ENDPOINTS: list[EndpointSpec] = [
    EndpointSpec("me", "GET", "/api/1/users/me"),
    EndpointSpec("region", "GET", "/api/1/users/region"),
    EndpointSpec("orders", "GET", "/api/1/users/orders"),
    EndpointSpec("feature_config", "GET", "/api/1/users/feature_config"),
]

# === PARTNER ENDPOINTS ===

PARTNER_ENDPOINTS: list[EndpointSpec] = [
    EndpointSpec("register", "POST", "/api/1/partner_accounts",
                 notes="Handled via auth.py partner_register"),
    EndpointSpec("public_key", "GET", "/api/1/partner_accounts/public_key",
                 [ParamSpec("domain", "str")]),
    EndpointSpec("fleet_telemetry_error_vins", "GET",
                 "/api/1/partner_accounts/fleet_telemetry_error_vins"),
    EndpointSpec("fleet_telemetry_errors", "GET",
                 "/api/1/partner_accounts/fleet_telemetry_errors"),
]

# fmt: on


# ---------------------------------------------------------------------------
# Introspection: extract method signatures from our API classes
# ---------------------------------------------------------------------------


def _get_api_methods(module_path: Path) -> dict[str, dict[str, Any]]:
    """Parse a Python file and extract async method signatures."""
    source = module_path.read_text()
    tree = ast.parse(source)
    methods: dict[str, dict[str, Any]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and not node.name.startswith("_"):
            params: dict[str, str] = {}
            for arg in node.args.args:
                if arg.arg in ("self", "vin", "site_id"):
                    continue
                type_str = ""
                if arg.annotation:
                    type_str = ast.unparse(arg.annotation)
                params[arg.arg] = type_str

            # keyword-only args
            for arg in node.args.kwonlyargs:
                type_str = ""
                if arg.annotation:
                    type_str = ast.unparse(arg.annotation)
                params[arg.arg] = type_str

            methods[node.name] = {
                "params": params,
                "lineno": node.lineno,
            }
    return methods


def _normalize_type(type_str: str) -> str:
    """Normalize Python type annotations for comparison."""
    type_str = type_str.strip()
    # Remove Optional/None union
    for prefix in ("dict[str, Any] | None", "str | None", "int | None", "float | None"):
        if type_str == prefix:
            return prefix.split(" |")[0]
    if type_str.startswith("dict"):
        return "dict"
    if type_str.startswith("list"):
        return "list"
    return type_str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    severity: str  # "ERROR", "WARNING", "INFO"
    category: str
    endpoint: str
    message: str


def validate_commands(
    spec_commands: list[EndpointSpec],
    api_methods: dict[str, dict[str, Any]],
) -> list[Issue]:
    """Compare command spec against actual API methods."""
    issues: list[Issue] = []

    for cmd in spec_commands:
        name = cmd.name
        if name == "wake_up":
            continue  # Handled by VehicleAPI.wake()

        if name not in api_methods:
            sev = "WARNING" if cmd.domain == "rest_only" else "ERROR"
            issues.append(Issue(sev, "MISSING_COMMAND", name,
                                f"Command '{name}' not implemented in CommandAPI"))
            continue

        method = api_methods[name]
        method_params = method["params"]

        # Check each expected parameter
        for param in cmd.params:
            # Handle dict pass-through (schedule params)
            if param.type == "dict" and param.name == "schedule":
                if "schedule" in method_params:
                    continue
                # Might use a different param name
                continue

            if param.name not in method_params:
                # Check for aliased names
                issues.append(Issue(
                    "ERROR", "WRONG_PARAM_NAME", name,
                    f"Expected param '{param.name}' (type={param.type}) "
                    f"not found. Have: {list(method_params.keys())} "
                    f"[line {method['lineno']}]"
                ))
                continue

            # Check type
            actual_type = _normalize_type(method_params[param.name])
            if param.type == "float" and actual_type == "int":
                issues.append(Issue(
                    "ERROR", "WRONG_PARAM_TYPE", name,
                    f"Param '{param.name}' should be float, is int "
                    f"[line {method['lineno']}]"
                ))
            elif param.type == "int" and actual_type == "float":
                issues.append(Issue(
                    "WARNING", "TYPE_MISMATCH", name,
                    f"Param '{param.name}' expected int, is float "
                    f"(may be intentional) [line {method['lineno']}]"
                ))

        # Check for extra params we send that aren't in spec
        spec_param_names = {p.name for p in cmd.params}
        for pname in method_params:
            if pname == "endpoints":  # query param, not body
                continue
            if pname not in spec_param_names:
                issues.append(Issue(
                    "WARNING", "EXTRA_PARAM", name,
                    f"Method has param '{pname}' not in Go SDK spec "
                    f"[line {method['lineno']}]"
                ))

    return issues


def validate_vehicle_endpoints(
    spec_endpoints: list[EndpointSpec],
    api_methods: dict[str, dict[str, Any]],
    sharing_methods: dict[str, dict[str, Any]],
) -> list[Issue]:
    """Check vehicle data endpoints against VehicleAPI + SharingAPI."""
    issues: list[Issue] = []
    all_methods = {**api_methods, **sharing_methods}

    # Map spec names to method names
    name_map = {
        "share_invites": "list_invites",
    }

    for ep in spec_endpoints:
        method_name = name_map.get(ep.name, ep.name)
        if method_name not in all_methods:
            sev = "INFO" if "fleet" in ep.name or "enterprise" in ep.name else "WARNING"
            issues.append(Issue(
                sev, "MISSING_ENDPOINT", ep.name,
                f"Vehicle endpoint '{ep.name}' ({ep.method} {ep.path}) "
                f"not implemented. {ep.notes or ''}"
            ))
    return issues


def validate_energy_endpoints(
    spec_endpoints: list[EndpointSpec],
    api_methods: dict[str, dict[str, Any]],
) -> list[Issue]:
    issues: list[Issue] = []
    for ep in spec_endpoints:
        if ep.name not in api_methods:
            issues.append(Issue(
                "WARNING", "MISSING_ENDPOINT", ep.name,
                f"Energy endpoint '{ep.name}' ({ep.method} {ep.path}) "
                f"not implemented. {ep.notes or ''}"
            ))
    return issues


def validate_user_endpoints(
    spec_endpoints: list[EndpointSpec],
    api_methods: dict[str, dict[str, Any]],
) -> list[Issue]:
    issues: list[Issue] = []
    for ep in spec_endpoints:
        if ep.name not in api_methods:
            issues.append(Issue(
                "WARNING", "MISSING_ENDPOINT", ep.name,
                f"User endpoint '{ep.name}' ({ep.method} {ep.path}) not implemented"
            ))
    return issues


def validate_protocol_registry(spec_commands: list[EndpointSpec]) -> list[Issue]:
    """Check that protocol registry matches Go SDK domain routing."""
    # Import here to access the actual registry
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from tescmd.protocol.commands import COMMAND_REGISTRY, CommandSpec
    from tescmd.protocol.protobuf.messages import Domain

    issues: list[Issue] = []
    domain_map = {
        "vcsec": Domain.DOMAIN_VEHICLE_SECURITY,
        "infotainment": Domain.DOMAIN_INFOTAINMENT,
        "unsigned": Domain.DOMAIN_BROADCAST,
        "rest_only": None,  # REST-only commands may or may not be in registry
    }

    for cmd in spec_commands:
        if cmd.name == "wake_up":
            continue
        if cmd.domain == "rest_only":
            # REST-only commands should NOT be in the signing registry
            if cmd.name in COMMAND_REGISTRY:
                spec = COMMAND_REGISTRY[cmd.name]
                if spec.requires_signing:
                    issues.append(Issue(
                        "WARNING", "REGISTRY_MISMATCH", cmd.name,
                        f"REST-only command '{cmd.name}' is in registry "
                        f"with requires_signing=True"
                    ))
            continue

        expected_domain = domain_map.get(cmd.domain)
        if expected_domain is None:
            continue

        if cmd.name not in COMMAND_REGISTRY:
            issues.append(Issue(
                "ERROR", "MISSING_REGISTRY", cmd.name,
                f"Command '{cmd.name}' not in COMMAND_REGISTRY "
                f"(expected domain={cmd.domain})"
            ))
            continue

        actual = COMMAND_REGISTRY[cmd.name]
        if actual.domain != expected_domain:
            issues.append(Issue(
                "ERROR", "WRONG_DOMAIN", cmd.name,
                f"Command '{cmd.name}' has domain={actual.domain.name}, "
                f"expected={expected_domain.name}"
            ))

    return issues


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    src = Path(__file__).resolve().parent.parent / "src" / "tescmd"

    print("=" * 72)
    print("Tesla Fleet API Coverage Validation")
    print("=" * 72)
    print()

    # Parse API modules
    command_methods = _get_api_methods(src / "api" / "command.py")
    vehicle_methods = _get_api_methods(src / "api" / "vehicle.py")
    energy_methods = _get_api_methods(src / "api" / "energy.py")
    user_methods = _get_api_methods(src / "api" / "user.py")
    sharing_methods = _get_api_methods(src / "api" / "sharing.py")

    all_issues: list[Issue] = []

    # 1. Validate vehicle commands
    print("─" * 72)
    print("1. VEHICLE COMMANDS (CommandAPI)")
    print("─" * 72)
    cmd_issues = validate_commands(VEHICLE_COMMANDS, command_methods)
    all_issues.extend(cmd_issues)
    _print_issues(cmd_issues, "commands")

    # 2. Validate vehicle data endpoints
    print("─" * 72)
    print("2. VEHICLE ENDPOINTS (VehicleAPI)")
    print("─" * 72)
    veh_issues = validate_vehicle_endpoints(
        VEHICLE_ENDPOINTS, vehicle_methods, sharing_methods
    )
    all_issues.extend(veh_issues)
    _print_issues(veh_issues, "vehicle endpoints")

    # 3. Validate energy endpoints
    print("─" * 72)
    print("3. ENERGY ENDPOINTS (EnergyAPI)")
    print("─" * 72)
    energy_issues = validate_energy_endpoints(ENERGY_ENDPOINTS, energy_methods)
    all_issues.extend(energy_issues)
    _print_issues(energy_issues, "energy endpoints")

    # 4. Validate user endpoints
    print("─" * 72)
    print("4. USER ENDPOINTS (UserAPI)")
    print("─" * 72)
    user_issues = validate_user_endpoints(USER_ENDPOINTS, user_methods)
    all_issues.extend(user_issues)
    _print_issues(user_issues, "user endpoints")

    # 5. Validate charging endpoints
    print("─" * 72)
    print("5. CHARGING ENDPOINTS")
    print("─" * 72)
    charging_issues = [
        Issue("INFO", "MISSING_ENDPOINT", ep.name,
              f"Charging endpoint '{ep.name}' not implemented. {ep.notes or ''}")
        for ep in CHARGING_ENDPOINTS
    ]
    all_issues.extend(charging_issues)
    _print_issues(charging_issues, "charging endpoints")

    # 6. Validate protocol registry
    print("─" * 72)
    print("6. PROTOCOL REGISTRY")
    print("─" * 72)
    reg_issues = validate_protocol_registry(VEHICLE_COMMANDS)
    all_issues.extend(reg_issues)
    _print_issues(reg_issues, "protocol registry")

    # Summary
    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    errors = [i for i in all_issues if i.severity == "ERROR"]
    warnings = [i for i in all_issues if i.severity == "WARNING"]
    infos = [i for i in all_issues if i.severity == "INFO"]
    print(f"  ERRORS:   {len(errors)}")
    print(f"  WARNINGS: {len(warnings)}")
    print(f"  INFO:     {len(infos)}")
    print()

    if errors:
        print("ERRORS (must fix):")
        for e in errors:
            print(f"  [{e.category}] {e.endpoint}: {e.message}")
        print()

    if warnings:
        print("WARNINGS (should fix):")
        for w in warnings:
            print(f"  [{w.category}] {w.endpoint}: {w.message}")
        print()

    if infos:
        print("INFO (optional/future):")
        for i in infos:
            print(f"  [{i.category}] {i.endpoint}: {i.message}")

    # Counts
    print()
    print("─" * 72)
    total_commands = len([c for c in VEHICLE_COMMANDS if c.name != "wake_up"])
    implemented = len([c for c in VEHICLE_COMMANDS
                       if c.name != "wake_up" and c.name in command_methods])
    print(f"Command coverage: {implemented}/{total_commands} "
          f"({100*implemented/total_commands:.0f}%)")

    total_veh = len(VEHICLE_ENDPOINTS)
    impl_veh = len([e for e in VEHICLE_ENDPOINTS
                    if e.name in vehicle_methods or e.name in sharing_methods
                    or e.name == "share_invites"])
    print(f"Vehicle endpoint coverage: {impl_veh}/{total_veh} "
          f"({100*impl_veh/total_veh:.0f}%)")

    total_energy = len(ENERGY_ENDPOINTS)
    impl_energy = len([e for e in ENERGY_ENDPOINTS if e.name in energy_methods])
    print(f"Energy endpoint coverage: {impl_energy}/{total_energy} "
          f"({100*impl_energy/total_energy:.0f}%)")

    total_user = len(USER_ENDPOINTS)
    impl_user = len([e for e in USER_ENDPOINTS if e.name in user_methods])
    print(f"User endpoint coverage: {impl_user}/{total_user} "
          f"({100*impl_user/total_user:.0f}%)")

    return 1 if errors else 0


def _print_issues(issues: list[Issue], section: str) -> None:
    if not issues:
        print(f"  All {section} OK")
    else:
        for issue in issues:
            marker = {"ERROR": "X", "WARNING": "!", "INFO": "i"}[issue.severity]
            print(f"  [{marker}] {issue.endpoint}: {issue.message}")
    print()


if __name__ == "__main__":
    sys.exit(main())
