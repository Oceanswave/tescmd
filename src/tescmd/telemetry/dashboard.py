"""Rich Live TUI dashboard for real-time telemetry display."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console, RenderableType
    from rich.live import Live

    from tescmd.output.rich_output import DisplayUnits
    from tescmd.telemetry.decoder import TelemetryFrame


class TelemetryDashboard:
    """Rich Live TUI renderer for streaming telemetry data."""

    def __init__(self, console: Console, units: DisplayUnits) -> None:
        self._console = console
        self._units = units
        self._state: dict[str, Any] = {}
        self._timestamps: dict[str, datetime] = {}
        self._frame_count: int = 0
        self._vin: str = ""
        self._started_at: datetime = datetime.now(tz=UTC)
        self._live: Live | None = None
        self._connected: bool = False
        self._tunnel_url: str = ""

    def update(self, frame: TelemetryFrame) -> None:
        """Ingest a telemetry frame and refresh the display."""
        self._frame_count += 1
        self._connected = True
        if frame.vin:
            self._vin = frame.vin

        for datum in frame.data:
            self._state[datum.field_name] = datum.value
            self._timestamps[datum.field_name] = frame.created_at

        # Trigger an immediate refresh so data appears without waiting for the
        # next auto-refresh tick.  We do NOT call live.update(self.render())
        # because that would replace the Live renderable with a static snapshot,
        # breaking the uptime counter between frames.  The Live object already
        # holds a reference to `self` (via __rich__), so refresh() re-renders
        # the dashboard with the freshly updated state.
        if self._live is not None:
            self._live.refresh()

    def set_live(self, live: Live) -> None:
        """Attach a Rich Live instance for auto-refresh."""
        self._live = live

    def set_tunnel_url(self, url: str) -> None:
        """Set the tunnel URL for display."""
        self._tunnel_url = url

    def __rich__(self) -> RenderableType:
        """Allow Rich Live to call render() on every refresh tick."""
        return self.render()

    def render(self) -> RenderableType:
        """Build the full dashboard renderable."""
        from rich.console import Group

        parts: list[RenderableType] = []

        # Header panel
        parts.append(self._render_header())

        # Data table
        if self._state:
            parts.append(self._render_data_table())
        else:
            parts.append(
                Panel(
                    "[dim]Waiting for telemetry data...[/dim]",
                    title="Telemetry Data",
                    border_style="dim",
                )
            )

        # Footer
        parts.append(self._render_footer())

        return Group(*parts)

    def _render_header(self) -> Panel:
        """Render the status header panel."""
        now = datetime.now(tz=UTC)
        uptime = now - self._started_at
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        status_style = "green" if self._connected else "yellow"
        status_text = "Connected" if self._connected else "Waiting"

        header = Text()
        header.append("VIN: ", style="bold")
        header.append(self._vin or "(waiting)", style="cyan")
        header.append("  |  Status: ", style="bold")
        header.append(status_text, style=status_style)
        header.append("  |  Frames: ", style="bold")
        header.append(str(self._frame_count), style="cyan")
        header.append("  |  Uptime: ", style="bold")
        header.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}", style="cyan")

        return Panel(header, title="Fleet Telemetry Stream", border_style="blue")

    def _render_data_table(self) -> Table:
        """Render the telemetry data table."""
        table = Table(title="Telemetry Data", expand=True)
        table.add_column("Field", style="bold", no_wrap=True)
        table.add_column("Value", style="cyan")
        table.add_column("Last Update", style="dim", no_wrap=True)

        for field_name in sorted(self._state.keys()):
            value = self._state[field_name]
            display_value = self._format_value(field_name, value)
            ts = self._timestamps.get(field_name)
            ts_str = ts.strftime("%H:%M:%S") if ts else ""
            table.add_row(field_name, display_value, ts_str)

        return table

    def _render_footer(self) -> Text:
        """Render the footer with stream URL and exit hint."""
        footer = Text()
        if self._tunnel_url:
            footer.append("  Stream: ", style="dim")
            footer.append(self._tunnel_url, style="dim cyan")
            footer.append("  |  ", style="dim")
        footer.append("Press q or Ctrl+C to stop", style="dim")
        return footer

    def _format_value(self, field_name: str, value: Any) -> str:
        """Format a telemetry value with unit conversion where applicable."""
        from tescmd.output.rich_output import DistanceUnit, PressureUnit, TempUnit

        if value is None:
            return "—"

        if isinstance(value, dict):
            # Location
            lat = value.get("latitude", 0.0)
            lng = value.get("longitude", 0.0)
            return f"{lat:.6f}, {lng:.6f}"

        if isinstance(value, bool):
            return "Yes" if value else "No"

        # Temperature fields (API returns Celsius)
        temp_fields = {
            "InsideTemp",
            "OutsideTemp",
            "HvacLeftTemperatureRequest",
            "HvacRightTemperatureRequest",
            "ModuleTempMax",
            "ModuleTempMin",
        }
        if field_name in temp_fields and isinstance(value, (int, float)):
            if self._units.temp == TempUnit.F:
                return f"{value * 9 / 5 + 32:.1f}°F"
            return f"{value:.1f}°C"

        # Distance fields (API returns miles)
        distance_fields = {
            "Odometer",
            "EstBatteryRange",
            "IdealBatteryRange",
            "RatedRange",
            "MilesToArrival",
        }
        if field_name in distance_fields and isinstance(value, (int, float)):
            if self._units.distance == DistanceUnit.KM:
                return f"{value * 1.60934:.1f} km"
            return f"{value:.1f} mi"

        # Speed fields (API returns mph)
        speed_fields = {"VehicleSpeed", "CruiseSetSpeed", "CurrentLimitMph"}
        if field_name in speed_fields and isinstance(value, (int, float)):
            if self._units.distance == DistanceUnit.KM:
                return f"{value * 1.60934:.0f} km/h"
            return f"{value:.0f} mph"

        # Pressure fields (API returns bar)
        pressure_fields = {
            "TpmsPressureFl",
            "TpmsPressureFr",
            "TpmsPressureRl",
            "TpmsPressureRr",
        }
        if field_name in pressure_fields and isinstance(value, (int, float)):
            if self._units.pressure == PressureUnit.PSI:
                return f"{value * 14.5038:.1f} psi"
            return f"{value:.2f} bar"

        # Percentage fields
        pct_fields = {"Soc", "BatteryLevel", "ChargeLimitSoc"}
        if field_name in pct_fields and isinstance(value, (int, float)):
            return f"{value}%"

        # Voltage / current
        if "Voltage" in field_name and isinstance(value, (int, float)):
            return f"{value:.1f} V"
        if ("Current" in field_name or "Amps" in field_name) and isinstance(value, (int, float)):
            return f"{value:.1f} A"

        # Power
        if "Power" in field_name and isinstance(value, (int, float)):
            return f"{value:.2f} kW"

        # Time-to-full
        if field_name == "TimeToFullCharge" and isinstance(value, (int, float)):
            hours = int(value)
            mins = int((value - hours) * 60)
            return f"{hours}h {mins}m" if hours else f"{mins}m"

        if isinstance(value, float):
            return f"{value:.2f}"

        return str(value)
