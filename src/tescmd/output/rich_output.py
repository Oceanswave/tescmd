from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from rich.console import Console

    from tescmd.models.energy import LiveStatus, SiteInfo
    from tescmd.models.user import UserInfo, UserRegion
    from tescmd.models.vehicle import (
        ChargeState,
        ClimateState,
        DriveState,
        GuiSettings,
        NearbyChargingSites,
        Vehicle,
        VehicleConfig,
        VehicleData,
        VehicleState,
    )


# -- Unit types --------------------------------------------------------


class PressureUnit(StrEnum):
    PSI = "psi"
    BAR = "bar"


class TempUnit(StrEnum):
    F = "F"
    C = "C"


class DistanceUnit(StrEnum):
    MI = "mi"
    KM = "km"


@dataclass(frozen=True)
class DisplayUnits:
    """Controls how values are displayed.  Defaults to US units."""

    pressure: PressureUnit = PressureUnit.PSI
    temp: TempUnit = TempUnit.F
    distance: DistanceUnit = DistanceUnit.MI


# -- Conversion constants ----------------------------------------------

_BAR_TO_PSI = 14.5038
_MI_TO_KM = 1.60934


class RichOutput:
    """Rich-based terminal output helpers for *tescmd*."""

    def __init__(self, console: Console, units: DisplayUnits | None = None) -> None:
        self._con = console
        self._units = units or DisplayUnits()

    # ------------------------------------------------------------------
    # Unit formatting helpers
    # ------------------------------------------------------------------

    def _fmt_temp(self, celsius: float) -> str:
        if self._units.temp == TempUnit.F:
            return f"{celsius * 9.0 / 5.0 + 32.0:.1f}\u00b0F"
        return f"{celsius:.1f}\u00b0C"

    def _fmt_dist(self, miles: float) -> str:
        if self._units.distance == DistanceUnit.KM:
            return f"{miles * _MI_TO_KM:.1f} km"
        return f"{miles} mi"

    def _fmt_odometer(self, miles: float) -> str:
        if self._units.distance == DistanceUnit.KM:
            return f"{miles * _MI_TO_KM:,.1f} km"
        return f"{miles:,.1f} mi"

    def _fmt_speed(self, mph: int) -> str:
        if self._units.distance == DistanceUnit.KM:
            return f"{mph * _MI_TO_KM:.0f} km/h"
        return f"{mph} mph"

    def _fmt_rate(self, mi_per_hr: float) -> str:
        if self._units.distance == DistanceUnit.KM:
            return f"{mi_per_hr * _MI_TO_KM:.1f} km/hr"
        return f"{mi_per_hr} mi/hr"

    def _fmt_pressure(self, bar: float) -> str:
        if self._units.pressure == PressureUnit.PSI:
            return f"{bar * _BAR_TO_PSI:.1f}"
        return f"{bar:.2f}"

    # ------------------------------------------------------------------
    # Generic dict → table helper
    # ------------------------------------------------------------------

    def _dict_table(self, title: str, data: dict[str, Any], *, empty_msg: str = "") -> None:
        """Render an arbitrary dict as a 2-column Field / Value table.

        * Nested dicts are flattened one level deep with dot notation.
        * Lists of scalars are comma-joined; lists of dicts show ``[N items]``.
        * ``None`` values are skipped.
        """
        if not data:
            self._con.print(empty_msg or "[dim]No data.[/dim]")
            return

        table = Table(title=title)
        table.add_column("Field", style="bold")
        table.add_column("Value")

        for key, val in data.items():
            if val is None:
                continue
            if isinstance(val, dict):
                for sub_key, sub_val in val.items():
                    if sub_val is not None:
                        table.add_row(f"{key}.{sub_key}", str(sub_val))
            elif isinstance(val, list):
                if not val:
                    table.add_row(key, "[]")
                elif isinstance(val[0], dict):
                    table.add_row(key, f"[{len(val)} items]")
                else:
                    table.add_row(key, ", ".join(str(v) for v in val))
            else:
                table.add_row(key, str(val))

        self._con.print(table)

    # -- Thin wrappers for specific dict-based endpoints ----------------

    def vehicle_subscriptions(self, data: dict[str, Any]) -> None:
        """Display subscription eligibility data."""
        self._dict_table(
            "Subscription Eligibility",
            data,
            empty_msg="[dim]No subscription eligibility data.[/dim]",
        )

    def vehicle_upgrades(self, data: dict[str, Any]) -> None:
        """Display upgrade eligibility data."""
        self._dict_table(
            "Upgrade Eligibility",
            data,
            empty_msg="[dim]No upgrade eligibility data.[/dim]",
        )

    def vehicle_options(self, data: dict[str, Any]) -> None:
        """Display vehicle option codes."""
        self._dict_table(
            "Vehicle Options",
            data,
            empty_msg="[dim]No option data available.[/dim]",
        )

    def vehicle_specs(self, data: dict[str, Any]) -> None:
        """Display vehicle specifications."""
        self._dict_table(
            "Vehicle Specifications",
            data,
            empty_msg="[dim]No spec data available.[/dim]",
        )

    def vehicle_warranty(self, data: dict[str, Any]) -> None:
        """Display warranty details."""
        self._dict_table(
            "Warranty Details",
            data,
            empty_msg="[dim]No warranty data available.[/dim]",
        )

    def fleet_status(self, data: dict[str, Any]) -> None:
        """Display fleet status."""
        self._dict_table(
            "Fleet Status",
            data,
            empty_msg="[dim]No fleet status data.[/dim]",
        )

    def telemetry_config(self, data: dict[str, Any]) -> None:
        """Display fleet telemetry configuration."""
        self._dict_table(
            "Fleet Telemetry Config",
            data,
            empty_msg="[dim]No telemetry config found.[/dim]",
        )

    def telemetry_errors(self, data: dict[str, Any]) -> None:
        """Display fleet telemetry errors."""
        self._dict_table(
            "Fleet Telemetry Errors",
            data,
            empty_msg="[dim]No telemetry errors found.[/dim]",
        )

    def vehicle_service(self, data: dict[str, Any]) -> None:
        """Display vehicle service data."""
        self._dict_table(
            "Service Data",
            data,
            empty_msg="[dim]No service data available.[/dim]",
        )

    def vehicle_release_notes(self, data: dict[str, Any]) -> None:
        """Display firmware release notes."""
        version = data.get("deployed_version") or data.get("release_notes_version", "")
        notes = data.get("release_notes", [])

        if not notes:
            self._con.print("[dim]No release notes available.[/dim]")
            return

        if version:
            self._con.print(f"[bold]Release Notes — {version}[/bold]")
            self._con.print()

        for note in notes:
            if not isinstance(note, dict):
                self._con.print(f"  {note}")
                continue
            title = note.get("title", "")
            desc = note.get("description", "")
            if title:
                self._con.print(f"[bold cyan]{title}[/bold cyan]")
            if desc:
                for line in desc.strip().splitlines():
                    self._con.print(f"  {line.strip()}")
                self._con.print()

    # ------------------------------------------------------------------
    # Vehicle list
    # ------------------------------------------------------------------

    def vehicle_list(self, vehicles: list[Vehicle]) -> None:
        """Print a table of vehicles."""
        table = Table(title="Vehicles")
        table.add_column("VIN", style="cyan")
        table.add_column("Name")
        table.add_column("State")
        table.add_column("ID", justify="right")

        for v in vehicles:
            state_style = "green" if v.state == "online" else "yellow"
            table.add_row(
                v.vin,
                v.display_name or "",
                f"[{state_style}]{v.state}[/{state_style}]",
                str(v.vehicle_id) if v.vehicle_id is not None else "",
            )

        self._con.print(table)

    # ------------------------------------------------------------------
    # Full vehicle data
    # ------------------------------------------------------------------

    def vehicle_data(self, data: VehicleData) -> None:
        """Print a panel containing all available vehicle data sections."""
        title = data.display_name or data.vin
        self._con.print(Panel(f"[bold]{title}[/bold]", expand=False))

        if data.vehicle_state is not None:
            self.vehicle_status(data.vehicle_state)
        if data.charge_state is not None:
            self.charge_status(data.charge_state)
        if data.climate_state is not None:
            self.climate_status(data.climate_state)
        if data.drive_state is not None:
            self.location(data.drive_state)
        elif data.state == "online":
            self.info("[dim]Location unavailable — vehicle command key not enrolled.[/dim]")
        if data.vehicle_config is not None:
            self.vehicle_config(data.vehicle_config)
        if data.gui_settings is not None:
            self.gui_settings(data.gui_settings)

    # ------------------------------------------------------------------
    # Charge status
    # ------------------------------------------------------------------

    def charge_status(self, cs: ChargeState) -> None:
        """Print a table of charge-related fields (non-None only)."""
        table = Table(title="Charge Status")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        rows: list[tuple[str, str]] = []
        if cs.battery_level is not None:
            rows.append(("Battery %", f"{cs.battery_level}%"))
        if cs.battery_range is not None:
            rows.append(("Range", self._fmt_dist(cs.battery_range)))
        if cs.charging_state is not None:
            state = cs.charging_state
            style = {
                "Charging": "green",
                "Complete": "cyan",
                "Disconnected": "dim",
                "Stopped": "yellow",
            }.get(state, "")
            label = f"[{style}]{state}[/{style}]" if style else state
            rows.append(("Status", label))
        if cs.charge_limit_soc is not None:
            rows.append(("Limit", f"{cs.charge_limit_soc}%"))
        if cs.charge_rate is not None and cs.charge_rate > 0:
            rows.append(("Rate", self._fmt_rate(cs.charge_rate)))
        if cs.charger_voltage is not None and cs.charger_voltage > 0:
            rows.append(("Voltage", f"{cs.charger_voltage} V"))
        if cs.charger_actual_current is not None and cs.charger_actual_current > 0:
            rows.append(("Current", f"{cs.charger_actual_current} A"))
        if cs.charger_type:
            rows.append(("Charger", cs.charger_type))
        if cs.minutes_to_full_charge is not None and cs.minutes_to_full_charge > 0:
            hours, mins = divmod(cs.minutes_to_full_charge, 60)
            if hours:
                rows.append(("Time remaining", f"{hours}h {mins}m"))
            else:
                rows.append(("Time remaining", f"{mins} min"))
        if cs.charge_port_door_open is not None:
            rows.append(("Port door", "open" if cs.charge_port_door_open else "closed"))
        if cs.ideal_battery_range is not None:
            rows.append(("Ideal range", self._fmt_dist(cs.ideal_battery_range)))
        if cs.usable_battery_level is not None and cs.usable_battery_level != cs.battery_level:
            rows.append(("Usable %", f"{cs.usable_battery_level}%"))
        if cs.charge_energy_added is not None and cs.charge_energy_added > 0:
            rows.append(("Energy added", f"{cs.charge_energy_added} kWh"))
        if cs.charge_miles_added_rated is not None and cs.charge_miles_added_rated > 0:
            rows.append(("Range added", self._fmt_dist(cs.charge_miles_added_rated)))
        if cs.charger_power is not None and cs.charger_power > 0:
            rows.append(("Charger power", f"{cs.charger_power} kW"))
        if cs.conn_charge_cable and cs.conn_charge_cable != "<invalid>":
            rows.append(("Cable", cs.conn_charge_cable))
        if cs.charge_port_latch:
            rows.append(("Port latch", cs.charge_port_latch))
        if cs.scheduled_charging_mode and cs.scheduled_charging_mode != "Off":
            rows.append(("Scheduled", cs.scheduled_charging_mode))
        if cs.battery_heater_on is True:
            rows.append(("Battery heater", "[green]on[/green]"))
        if cs.preconditioning_enabled is True:
            rows.append(("Preconditioning", "[green]on[/green]"))
        if cs.est_battery_range is not None:
            rows.append(("Est. range", self._fmt_dist(cs.est_battery_range)))
        if (
            cs.time_to_full_charge is not None
            and cs.time_to_full_charge > 0
            and cs.minutes_to_full_charge is None
        ):
            rows.append(("Time to full", f"{cs.time_to_full_charge:.1f}h"))
        if cs.scheduled_charging_start_time is not None:
            from datetime import UTC

            rows.append(
                (
                    "Scheduled start",
                    datetime.fromtimestamp(cs.scheduled_charging_start_time, tz=UTC)
                    .astimezone()
                    .strftime("%I:%M %p"),
                )
            )
        if cs.scheduled_departure_time_minutes is not None:
            h, m = divmod(cs.scheduled_departure_time_minutes, 60)
            rows.append(("Scheduled departure", f"{h:02d}:{m:02d}"))

        for field, value in rows:
            table.add_row(field, value)

        self._con.print(table)

    # ------------------------------------------------------------------
    # Climate status
    # ------------------------------------------------------------------

    def climate_status(self, cs: ClimateState) -> None:
        """Print a table of climate-related fields."""
        table = Table(title="Climate Status")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if cs.inside_temp is not None:
            table.add_row("Inside temp", self._fmt_temp(cs.inside_temp))
        if cs.outside_temp is not None:
            table.add_row("Outside temp", self._fmt_temp(cs.outside_temp))
        if cs.driver_temp_setting is not None:
            table.add_row("Driver temp", self._fmt_temp(cs.driver_temp_setting))
        if cs.passenger_temp_setting is not None:
            table.add_row("Passenger temp", self._fmt_temp(cs.passenger_temp_setting))
        if cs.is_climate_on is not None:
            on = cs.is_climate_on
            table.add_row("HVAC", "[green]on[/green]" if on else "off")
        if cs.fan_status is not None and cs.fan_status > 0:
            table.add_row("Fan speed", str(cs.fan_status))
        if cs.defrost_mode is not None and cs.defrost_mode > 0:
            table.add_row("Defrost", "on")
        if cs.seat_heater_left is not None and cs.seat_heater_left > 0:
            table.add_row("Seat heater L", _heat_level(cs.seat_heater_left))
        if cs.seat_heater_right is not None and cs.seat_heater_right > 0:
            table.add_row("Seat heater R", _heat_level(cs.seat_heater_right))
        if cs.steering_wheel_heater is True:
            table.add_row("Wheel heater", "on")
        if cs.cabin_overheat_protection:
            cop = cs.cabin_overheat_protection
            if cs.cabin_overheat_protection_actively_cooling is True:
                cop = f"[green]{cop}[/green]"
            table.add_row("Cabin overheat", cop)
        if cs.is_auto_conditioning_on is True:
            table.add_row("Auto conditioning", "on")
        if cs.is_preconditioning is True:
            table.add_row("Preconditioning", "on")
        if cs.seat_heater_rear_left is not None and cs.seat_heater_rear_left > 0:
            table.add_row("Seat heater RL", _heat_level(cs.seat_heater_rear_left))
        if cs.seat_heater_rear_center is not None and cs.seat_heater_rear_center > 0:
            table.add_row("Seat heater RC", _heat_level(cs.seat_heater_rear_center))
        if cs.seat_heater_rear_right is not None and cs.seat_heater_rear_right > 0:
            table.add_row("Seat heater RR", _heat_level(cs.seat_heater_rear_right))
        if cs.bioweapon_defense_mode is True:
            table.add_row("Bio-defense", "[green]on[/green]")

        self._con.print(table)

    # ------------------------------------------------------------------
    # Location / drive state
    # ------------------------------------------------------------------

    def location(self, ds: DriveState) -> None:
        """Print a table of GPS location fields."""
        table = Table(title="Location")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if ds.latitude is not None and ds.longitude is not None:
            table.add_row("Latitude", str(ds.latitude))
            table.add_row("Longitude", str(ds.longitude))
        if ds.heading is not None:
            table.add_row("Heading", f"{ds.heading}\u00b0")
        if ds.timestamp is not None:
            table.add_row(
                "Updated",
                datetime.fromtimestamp(ds.timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S"),
            )

        # Show any additional location fields from the API (extra="allow")
        _known = {
            "latitude",
            "longitude",
            "heading",
            "timestamp",
            "shift_state",
            "speed",
            "power",
        }
        for key, value in sorted((ds.model_extra or {}).items()):
            if key not in _known and value is not None:
                label = key.replace("_", " ").title()
                table.add_row(label, str(value))

        self._con.print(table)

    # ------------------------------------------------------------------
    # Vehicle state
    # ------------------------------------------------------------------

    def vehicle_status(self, vs: VehicleState) -> None:
        """Print a table of vehicle state fields."""
        table = Table(title="Vehicle Status")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if vs.locked is not None:
            locked = vs.locked
            table.add_row(
                "Locked",
                "[green]yes[/green]" if locked else "[yellow]no[/yellow]",
            )
        if vs.sentry_mode is not None:
            on = vs.sentry_mode
            table.add_row("Sentry mode", "[green]on[/green]" if on else "off")
        if vs.odometer is not None:
            table.add_row("Odometer", self._fmt_odometer(vs.odometer))
        if vs.car_version:
            table.add_row("Software", vs.car_version)

        # Doors (only show if any data present)
        doors = _door_summary(vs)
        if doors:
            table.add_row("Doors", doors)

        # Windows (only show if any data present)
        windows = _window_summary(vs)
        if windows:
            table.add_row("Windows", windows)

        # Trunks
        if vs.ft is not None:
            table.add_row("Frunk", "[yellow]open[/yellow]" if vs.ft else "closed")
        if vs.rt is not None:
            table.add_row("Trunk", "[yellow]open[/yellow]" if vs.rt else "closed")

        # Additional state
        if vs.center_display_state is not None:
            table.add_row("Center display", "on" if vs.center_display_state >= 2 else "off")
        if vs.dashcam_state:
            table.add_row("Dashcam", vs.dashcam_state)
        if vs.remote_start_enabled is True:
            table.add_row("Remote start", "[green]enabled[/green]")
        if vs.is_user_present is True:
            table.add_row("User present", "yes")
        if vs.homelink_nearby is True:
            table.add_row("Homelink", "nearby")

        # Tire pressure (API returns bar)
        tpms = [vs.tpms_pressure_fl, vs.tpms_pressure_fr, vs.tpms_pressure_rl, vs.tpms_pressure_rr]
        if any(p is not None for p in tpms):
            parts: list[str] = []
            for label, val in [
                ("FL", vs.tpms_pressure_fl),
                ("FR", vs.tpms_pressure_fr),
                ("RL", vs.tpms_pressure_rl),
                ("RR", vs.tpms_pressure_rr),
            ]:
                if val is not None:
                    parts.append(f"{label}: {self._fmt_pressure(val)}")
                else:
                    parts.append(f"{label}: --")
            table.add_row(f"Tire pressure ({self._units.pressure})", ", ".join(parts))

        self._con.print(table)

    # ------------------------------------------------------------------
    # Vehicle config
    # ------------------------------------------------------------------

    def vehicle_config(self, vc: VehicleConfig) -> None:
        """Print a table of vehicle configuration fields."""
        table = Table(title="Vehicle Config")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if vc.car_type:
            table.add_row("Model", vc.car_type)
        if vc.trim_badging:
            table.add_row("Trim", vc.trim_badging)
        if vc.exterior_color:
            table.add_row("Color", vc.exterior_color)
        if vc.wheel_type:
            table.add_row("Wheels", vc.wheel_type)
        if vc.roof_color:
            table.add_row("Roof", vc.roof_color)
        if vc.can_accept_navigation_requests is True:
            table.add_row("Navigation", "yes")
        if vc.can_actuate_trunks is True:
            table.add_row("Trunk actuation", "yes")
        if vc.has_seat_cooling is True:
            table.add_row("Seat cooling", "yes")
        if vc.motorized_charge_port is True:
            table.add_row("Motorized port", "yes")
        if vc.plg is True:
            table.add_row("Power liftgate", "yes")
        if vc.eu_vehicle is True:
            table.add_row("EU vehicle", "yes")

        self._con.print(table)

    # ------------------------------------------------------------------
    # GUI settings
    # ------------------------------------------------------------------

    def gui_settings(self, gs: GuiSettings) -> None:
        """Print a table of display / GUI settings."""
        table = Table(title="Display Settings")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if gs.gui_distance_units:
            table.add_row("Distance units", gs.gui_distance_units)
        if gs.gui_temperature_units:
            table.add_row("Temperature units", gs.gui_temperature_units)
        if gs.gui_charge_rate_units:
            table.add_row("Charge rate units", gs.gui_charge_rate_units)

        self._con.print(table)

    # ------------------------------------------------------------------
    # Command result helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Software status
    # ------------------------------------------------------------------

    def software_status(self, vs: VehicleState) -> None:
        """Print a table of software version and update status."""
        table = Table(title="Software Status")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if vs.car_version:
            table.add_row("Current version", vs.car_version)

        su = vs.software_update
        if su:
            if su.status:
                style = {"available": "yellow", "installing": "green", "scheduled": "cyan"}.get(
                    su.status, ""
                )
                label = f"[{style}]{su.status}[/{style}]" if style else su.status
                table.add_row("Update status", label)
            if su.version:
                table.add_row("Available version", su.version)
            if su.install_perc is not None:
                table.add_row("Install progress", f"{su.install_perc}%")
            if su.expected_duration_sec is not None:
                table.add_row("Expected duration", f"{su.expected_duration_sec // 60}m")
        else:
            table.add_row("Update status", "[dim]up to date[/dim]")

        self._con.print(table)

    # ------------------------------------------------------------------
    # Nearby chargers
    # ------------------------------------------------------------------

    def nearby_chargers(self, data: NearbyChargingSites) -> None:
        """Print nearby charging sites."""
        if data.superchargers:
            table = Table(title="Nearby Superchargers")
            table.add_column("Name")
            table.add_column("Distance", justify="right")
            table.add_column("Stalls", justify="right")
            table.add_column("Available", justify="right")
            for sc in data.superchargers[:10]:
                table.add_row(
                    sc.name or "",
                    f"{sc.distance_miles:.1f} mi" if sc.distance_miles is not None else "",
                    str(sc.total_stalls) if sc.total_stalls is not None else "",
                    str(sc.available_stalls) if sc.available_stalls is not None else "",
                )
            self._con.print(table)

        if data.destination_charging:
            table = Table(title="Nearby Destination Chargers")
            table.add_column("Name")
            table.add_column("Distance", justify="right")
            for dc in data.destination_charging[:10]:
                table.add_row(
                    dc.name or "",
                    f"{dc.distance_miles:.1f} mi" if dc.distance_miles is not None else "",
                )
            self._con.print(table)

        if not data.superchargers and not data.destination_charging:
            self.info("[dim]No nearby charging sites found.[/dim]")

    # ------------------------------------------------------------------
    # Energy site display
    # ------------------------------------------------------------------

    def energy_site_list(self, sites: list[dict[str, Any]]) -> None:
        """Print a table of energy products (Powerwall, Solar, etc.)."""
        table = Table(title="Energy Products")
        table.add_column("Site ID", style="cyan")
        table.add_column("Name")
        table.add_column("Type")
        for s in sites:
            table.add_row(
                str(s.get("energy_site_id", "")),
                s.get("site_name", ""),
                s.get("resource_type", ""),
            )
        self._con.print(table)

    def energy_live_status(self, data: LiveStatus) -> None:
        """Print real-time power flow for an energy site."""
        table = Table(title="Energy Live Status")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        for val, label in [
            (data.solar_power, "Solar"),
            (data.battery_power, "Battery"),
            (data.grid_power, "Grid"),
            (data.load_power, "Home"),
        ]:
            if val is not None:
                table.add_row(label, f"{val / 1000:.2f} kW")

        if data.grid_status:
            table.add_row("Grid status", data.grid_status)

        battery_pct = data.percentage_charged or data.battery_level
        if battery_pct is not None:
            table.add_row("Battery %", f"{battery_pct:.0f}%")

        self._con.print(table)

    def energy_site_info(self, data: SiteInfo) -> None:
        """Print energy site configuration."""
        table = Table(title="Energy Site Info")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if data.site_name is not None:
            table.add_row("Name", data.site_name)
        if data.energy_site_id is not None:
            table.add_row("Site ID", str(data.energy_site_id))
        if data.resource_type is not None:
            table.add_row("Type", data.resource_type)
        if data.backup_reserve_percent is not None:
            table.add_row("Backup reserve", f"{data.backup_reserve_percent}%")
        if data.default_real_mode is not None:
            table.add_row("Operation mode", data.default_real_mode)
        if data.storm_mode_enabled is not None:
            table.add_row(
                "Storm watch",
                "[green]on[/green]" if data.storm_mode_enabled else "off",
            )

        self._con.print(table)

    # ------------------------------------------------------------------
    # User info display
    # ------------------------------------------------------------------

    def user_info(self, data: UserInfo) -> None:
        """Print user account information."""
        table = Table(title="User Info")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if data.email:
            table.add_row("Email", data.email)
        if data.full_name:
            table.add_row("Name", data.full_name)
        if data.profile_image_url:
            table.add_row("Avatar", data.profile_image_url)

        self._con.print(table)

    def user_region(self, data: UserRegion) -> None:
        """Print user's regional endpoint."""
        table = Table(title="Region")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if data.region:
            table.add_row("Region", data.region)
        if data.fleet_api_base_url:
            table.add_row("Fleet API URL", data.fleet_api_base_url)

        self._con.print(table)

    # ------------------------------------------------------------------
    # Command result helpers
    # ------------------------------------------------------------------

    def command_result(self, success: bool, message: str = "") -> None:
        """Print a coloured OK / FAILED indicator."""
        text = "[green]OK[/green]" if success else "[red]FAILED[/red]"
        if message:
            text += f"  {message}"
        self._con.print(text)

    def error(self, message: str) -> None:
        """Print a bold red error line."""
        from rich.markup import escape

        self._con.print(f"[bold red]Error:[/bold red] {escape(message)}")

    def info(self, message: str) -> None:
        """Print an informational message (plain)."""
        self._con.print(message)


# ----------------------------------------------------------------------
# Helpers (module-level, used by RichOutput methods)
# ----------------------------------------------------------------------


def _heat_level(level: int) -> str:
    """Convert a seat/wheel heater level (0-3) to a readable label."""
    return {1: "low", 2: "med", 3: "high"}.get(level, str(level))


def _door_summary(vs: VehicleState) -> str:
    """Return a compact summary of open doors, or empty string if all closed."""
    open_doors: list[str] = []
    if vs.door_driver_front:
        open_doors.append("FL")
    if vs.door_driver_rear:
        open_doors.append("RL")
    if vs.door_passenger_front:
        open_doors.append("FR")
    if vs.door_passenger_rear:
        open_doors.append("RR")
    if open_doors:
        return f"[yellow]{', '.join(open_doors)} open[/yellow]"
    # Only show "all closed" if we actually have door data
    has_data = any(
        getattr(vs, f) is not None
        for f in (
            "door_driver_front",
            "door_driver_rear",
            "door_passenger_front",
            "door_passenger_rear",
        )
    )
    return "all closed" if has_data else ""


def _window_summary(vs: VehicleState) -> str:
    """Return a compact summary of open windows, or empty string if all closed."""
    open_wins: list[str] = []
    if vs.window_driver_front:
        open_wins.append("FL")
    if vs.window_driver_rear:
        open_wins.append("RL")
    if vs.window_passenger_front:
        open_wins.append("FR")
    if vs.window_passenger_rear:
        open_wins.append("RR")
    if open_wins:
        return f"[yellow]{', '.join(open_wins)} open[/yellow]"
    has_data = any(
        getattr(vs, f) is not None
        for f in (
            "window_driver_front",
            "window_driver_rear",
            "window_passenger_front",
            "window_passenger_rear",
        )
    )
    return "all closed" if has_data else ""
