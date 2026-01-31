"""Tests for TelemetryDashboard — Rich Live TUI rendering."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

from rich.console import Console

from tescmd.output.rich_output import DisplayUnits, DistanceUnit, PressureUnit, TempUnit
from tescmd.telemetry.dashboard import TelemetryDashboard
from tescmd.telemetry.decoder import TelemetryDatum, TelemetryFrame


def _make_frame(
    data: list[TelemetryDatum] | None = None,
    vin: str = "5YJ3E1EA1NF000001",
) -> TelemetryFrame:
    return TelemetryFrame(
        vin=vin,
        created_at=datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC),
        data=data or [],
    )


class TestDashboardEmpty:
    def test_render_empty(self) -> None:
        console = Console(file=StringIO(), width=120)
        dashboard = TelemetryDashboard(console, DisplayUnits())
        renderable = dashboard.render()
        # Just verify it doesn't crash
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "Waiting for telemetry data" in output


class TestDashboardUpdate:
    def test_update_with_data(self) -> None:
        console = Console(file=StringIO(), width=120)
        dashboard = TelemetryDashboard(console, DisplayUnits())

        frame = _make_frame(
            data=[
                TelemetryDatum(field_name="BatteryLevel", field_id=8, value=72, value_type="int"),
                TelemetryDatum(field_name="VehicleSpeed", field_id=4, value=65, value_type="int"),
            ]
        )
        dashboard.update(frame)

        assert dashboard._frame_count == 1
        assert dashboard._vin == "5YJ3E1EA1NF000001"
        assert dashboard._state["BatteryLevel"] == 72
        assert dashboard._state["VehicleSpeed"] == 65

    def test_render_after_update(self) -> None:
        console = Console(file=StringIO(), width=120)
        dashboard = TelemetryDashboard(console, DisplayUnits())

        frame = _make_frame(
            data=[
                TelemetryDatum(field_name="Soc", field_id=3, value=85, value_type="int"),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "Soc" in output
        assert "85%" in output


class TestDashboardUnitConversion:
    def test_temperature_fahrenheit(self) -> None:
        console = Console(file=StringIO(), width=120)
        units = DisplayUnits(temp=TempUnit.F)
        dashboard = TelemetryDashboard(console, units)

        frame = _make_frame(
            data=[
                TelemetryDatum(
                    field_name="InsideTemp", field_id=33, value=22.0, value_type="float"
                ),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        # 22°C = 71.6°F
        assert "71.6°F" in output

    def test_temperature_celsius(self) -> None:
        console = Console(file=StringIO(), width=120)
        units = DisplayUnits(temp=TempUnit.C)
        dashboard = TelemetryDashboard(console, units)

        frame = _make_frame(
            data=[
                TelemetryDatum(
                    field_name="InsideTemp", field_id=33, value=22.0, value_type="float"
                ),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "22.0°C" in output

    def test_distance_km(self) -> None:
        console = Console(file=StringIO(), width=120)
        units = DisplayUnits(distance=DistanceUnit.KM)
        dashboard = TelemetryDashboard(console, units)

        frame = _make_frame(
            data=[
                TelemetryDatum(
                    field_name="Odometer", field_id=5, value=12345.6, value_type="float"
                ),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        # 12345.6 mi * 1.60934 ≈ 19871.1 km
        assert "km" in output

    def test_pressure_psi(self) -> None:
        console = Console(file=StringIO(), width=120)
        units = DisplayUnits(pressure=PressureUnit.PSI)
        dashboard = TelemetryDashboard(console, units)

        frame = _make_frame(
            data=[
                TelemetryDatum(
                    field_name="TpmsPressureFl", field_id=61, value=2.4, value_type="float"
                ),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        # 2.4 bar * 14.5038 ≈ 34.8 psi
        assert "psi" in output

    def test_pressure_bar(self) -> None:
        console = Console(file=StringIO(), width=120)
        units = DisplayUnits(pressure=PressureUnit.BAR)
        dashboard = TelemetryDashboard(console, units)

        frame = _make_frame(
            data=[
                TelemetryDatum(
                    field_name="TpmsPressureFl", field_id=61, value=2.4, value_type="float"
                ),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "bar" in output


class TestDashboardSpecialValues:
    def test_location_formatting(self) -> None:
        console = Console(file=StringIO(), width=120)
        dashboard = TelemetryDashboard(console, DisplayUnits())

        frame = _make_frame(
            data=[
                TelemetryDatum(
                    field_name="Location",
                    field_id=9,
                    value={"latitude": 37.7749, "longitude": -122.4194},
                    value_type="location",
                ),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "37.774" in output
        assert "-122.419" in output

    def test_bool_formatting(self) -> None:
        console = Console(file=StringIO(), width=120)
        dashboard = TelemetryDashboard(console, DisplayUnits())

        frame = _make_frame(
            data=[
                TelemetryDatum(field_name="Locked", field_id=51, value=True, value_type="bool"),
            ]
        )
        dashboard.update(frame)

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "Yes" in output

    def test_funnel_url_in_footer(self) -> None:
        console = Console(file=StringIO(), width=120)
        dashboard = TelemetryDashboard(console, DisplayUnits())
        dashboard.set_funnel_url("https://mybox.tail.ts.net")

        renderable = dashboard.render()
        console.print(renderable)
        output = console.file.getvalue()  # type: ignore[union-attr]
        assert "mybox.tail.ts.net" in output
