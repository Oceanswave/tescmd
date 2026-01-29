from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from rich.console import Console

    from tescmd.models.vehicle import (
        ChargeState,
        ClimateState,
        DriveState,
        Vehicle,
        VehicleData,
    )


class RichOutput:
    """Rich-based terminal output helpers for *tescmd*."""

    def __init__(self, console: Console) -> None:
        self._con = console

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

        if data.charge_state is not None:
            self.charge_status(data.charge_state)
        if data.climate_state is not None:
            self.climate_status(data.climate_state)
        if data.drive_state is not None:
            self.location(data.drive_state)

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
            rows.append(("Range", f"{cs.battery_range} mi"))
        if cs.charging_state is not None:
            rows.append(("Status", cs.charging_state))
        if cs.charge_limit_soc is not None:
            rows.append(("Limit", f"{cs.charge_limit_soc}%"))
        if cs.charge_rate is not None:
            rows.append(("Rate", f"{cs.charge_rate} mi/hr"))
        if cs.minutes_to_full_charge is not None:
            rows.append(("Time remaining", f"{cs.minutes_to_full_charge} min"))

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
            table.add_row("Inside temp", f"{cs.inside_temp}\u00b0")
        if cs.outside_temp is not None:
            table.add_row("Outside temp", f"{cs.outside_temp}\u00b0")
        if cs.driver_temp_setting is not None:
            table.add_row("Set temp", f"{cs.driver_temp_setting}\u00b0")
        if cs.is_climate_on is not None:
            label = "on" if cs.is_climate_on else "off"
            table.add_row("HVAC", label)

        self._con.print(table)

    # ------------------------------------------------------------------
    # Location / drive state
    # ------------------------------------------------------------------

    def location(self, ds: DriveState) -> None:
        """Print a table of drive-state / location fields."""
        table = Table(title="Location")
        table.add_column("Field", style="bold")
        table.add_column("Value")

        if ds.latitude is not None and ds.longitude is not None:
            table.add_row("Coordinates", f"{ds.latitude}, {ds.longitude}")
        if ds.heading is not None:
            table.add_row("Heading", f"{ds.heading}\u00b0")
        if ds.speed is not None:
            table.add_row("Speed", f"{ds.speed} mph")

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
        self._con.print(f"[bold red]Error:[/bold red] {message}")

    def info(self, message: str) -> None:
        """Print an informational message (plain)."""
        self._con.print(message)
