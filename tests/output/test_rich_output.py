from __future__ import annotations

from io import StringIO

from rich.console import Console

from tescmd.models.vehicle import (
    ChargeState,
    ClimateState,
    DriveState,
    Vehicle,
    VehicleData,
)
from tescmd.output.rich_output import RichOutput


def _make_console() -> tuple[Console, StringIO]:
    """Return a ``(Console, buffer)`` pair for capturing Rich output."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    return console, buf


class TestVehicleList:
    def test_renders_table_with_vehicles(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vehicles = [
            Vehicle(vin="5YJ3E1EA1NF000001", display_name="My Tesla", state="online", vehicle_id=1),
            Vehicle(vin="5YJ3E1EA1NF000002", display_name="Other", state="asleep", vehicle_id=2),
        ]
        ro.vehicle_list(vehicles)
        output = buf.getvalue()

        assert "5YJ3E1EA1NF000001" in output
        assert "My Tesla" in output
        assert "online" in output
        assert "5YJ3E1EA1NF000002" in output
        assert "asleep" in output

    def test_handles_none_display_name(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vehicles = [Vehicle(vin="5YJ3E1EA1NF000001")]
        ro.vehicle_list(vehicles)
        output = buf.getvalue()

        assert "5YJ3E1EA1NF000001" in output


class TestVehicleData:
    def test_renders_all_sections(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vd = VehicleData(
            vin="5YJ3E1EA1NF000001",
            display_name="My Tesla",
            charge_state=ChargeState(battery_level=80, charging_state="Complete"),
            climate_state=ClimateState(inside_temp=22.5, is_climate_on=True),
            drive_state=DriveState(latitude=37.394, longitude=-122.150, heading=90),
        )
        ro.vehicle_data(vd)
        output = buf.getvalue()

        # Panel title
        assert "My Tesla" in output
        # Charge section
        assert "80%" in output
        assert "Complete" in output
        # Climate section
        assert "22.5" in output
        assert "on" in output
        # Location section
        assert "37.394" in output
        assert "-122.15" in output

    def test_omits_missing_sections(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vd = VehicleData(vin="5YJ3E1EA1NF000001")
        ro.vehicle_data(vd)
        output = buf.getvalue()

        # Should still render the panel, but no sub-tables
        assert "5YJ3E1EA1NF000001" in output
        assert "Charge Status" not in output
        assert "Climate Status" not in output
        assert "Location" not in output


class TestLocation:
    def test_renders_coordinates_and_heading(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        ds = DriveState(latitude=37.394, longitude=-122.150, heading=270, speed=65)
        ro.location(ds)
        output = buf.getvalue()

        assert "37.394" in output
        assert "-122.15" in output
        assert "270" in output
        assert "65" in output


class TestChargeStatus:
    def test_renders_charge_fields(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        cs = ChargeState(
            battery_level=90,
            battery_range=250.5,
            charging_state="Charging",
            charge_limit_soc=95,
            charge_rate=32.0,
            minutes_to_full_charge=45,
        )
        ro.charge_status(cs)
        output = buf.getvalue()

        assert "90%" in output
        assert "250.5" in output
        assert "Charging" in output
        assert "95%" in output
        assert "32.0" in output
        assert "45 min" in output


class TestClimateStatus:
    def test_renders_climate_fields(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        cs = ClimateState(
            inside_temp=21.0,
            outside_temp=15.5,
            driver_temp_setting=22.0,
            is_climate_on=False,
        )
        ro.climate_status(cs)
        output = buf.getvalue()

        assert "21.0" in output
        assert "15.5" in output
        assert "22.0" in output
        assert "off" in output


class TestCommandResult:
    def test_success(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        ro.command_result(True)
        output = buf.getvalue()
        assert "OK" in output

    def test_failure_with_message(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        ro.command_result(False, "vehicle is asleep")
        output = buf.getvalue()
        assert "FAILED" in output
        assert "vehicle is asleep" in output


class TestErrorAndInfo:
    def test_error(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        ro.error("something went wrong")
        output = buf.getvalue()
        assert "Error:" in output
        assert "something went wrong" in output

    def test_info(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        ro.info("hello world")
        output = buf.getvalue()
        assert "hello world" in output
