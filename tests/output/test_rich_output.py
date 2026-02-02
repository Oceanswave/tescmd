from __future__ import annotations

from io import StringIO

from rich.console import Console

from tescmd.models.vehicle import (
    ChargeState,
    ClimateState,
    DriveState,
    GuiSettings,
    Vehicle,
    VehicleConfig,
    VehicleData,
    VehicleState,
)
from tescmd.output.rich_output import (
    DisplayUnits,
    DistanceUnit,
    PressureUnit,
    RichOutput,
    TempUnit,
)


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
            Vehicle(
                vin="5YJ3E1EA1NF000001", display_name="My Tesla", state="online", vehicle_id=1
            ),
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
        # Climate section (22.5°C → 72.5°F with default US units)
        assert "72.5" in output
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

        ds = DriveState(latitude=37.394, longitude=-122.150, heading=270)
        ro.location(ds)
        output = buf.getvalue()

        assert "37.394" in output
        assert "-122.15" in output
        assert "270" in output

    def test_renders_timestamp(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        # 1700000000000 ms = 2023-11-14 (exact date depends on TZ)
        ds = DriveState(latitude=37.394, longitude=-122.150, timestamp=1700000000000)
        ro.location(ds)
        output = buf.getvalue()

        assert "Updated" in output
        assert "2023-11-14" in output


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

    def test_renders_extended_charge_fields(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        cs = ChargeState(
            battery_level=80,
            ideal_battery_range=260.0,
            charge_energy_added=15.5,
            charger_power=48,
            conn_charge_cable="SAE",
            battery_heater_on=True,
        )
        ro.charge_status(cs)
        output = buf.getvalue()

        assert "260.0" in output
        assert "15.5" in output
        assert "48" in output
        assert "SAE" in output
        assert "Battery heater" in output

    def test_renders_est_range_and_schedule(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        cs = ChargeState(
            battery_level=70,
            est_battery_range=200.5,
            time_to_full_charge=2.5,
            scheduled_charging_start_time=1700000000,
            scheduled_departure_time_minutes=510,  # 8:30 AM
        )
        ro.charge_status(cs)
        output = buf.getvalue()

        assert "Est. range" in output
        assert "200.5" in output
        assert "2.5h" in output
        assert "Scheduled start" in output
        assert "Scheduled departure" in output
        assert "08:30" in output

    def test_time_to_full_skipped_when_minutes_present(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        cs = ChargeState(
            battery_level=70,
            minutes_to_full_charge=90,
            time_to_full_charge=1.5,
        )
        ro.charge_status(cs)
        output = buf.getvalue()

        # minutes_to_full_charge is present, so time_to_full_charge row is skipped
        assert "Time to full" not in output
        assert "Time remaining" in output

    def test_skips_invalid_cable(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        cs = ChargeState(conn_charge_cable="<invalid>")
        ro.charge_status(cs)
        output = buf.getvalue()

        assert "<invalid>" not in output


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

        # Temps converted: 21.0°C→69.8°F, 15.5°C→59.9°F, 22.0°C→71.6°F
        assert "69.8" in output
        assert "59.9" in output
        assert "71.6" in output
        assert "off" in output

    def test_renders_extended_climate_fields(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        cs = ClimateState(
            inside_temp=22.0,
            cabin_overheat_protection="On",
            seat_heater_rear_left=2,
            bioweapon_defense_mode=True,
        )
        ro.climate_status(cs)
        output = buf.getvalue()

        assert "Cabin overheat" in output
        assert "On" in output
        assert "med" in output
        assert "Bio-defense" in output


class TestVehicleStatus:
    def test_renders_trunks_and_tpms(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vs = VehicleState(
            locked=True,
            ft=0,
            rt=1,
            tpms_pressure_fl=2.9,
            tpms_pressure_fr=3.0,
            tpms_pressure_rl=2.8,
            tpms_pressure_rr=2.9,
            dashcam_state="Recording",
        )
        ro.vehicle_status(vs)
        output = buf.getvalue()

        assert "Frunk" in output
        assert "closed" in output
        assert "Trunk" in output
        # TPMS values converted from bar to PSI: 2.9 bar ≈ 42.1, 3.0 bar ≈ 43.5
        assert "42.1" in output
        assert "43.5" in output
        assert "psi" in output
        assert "Recording" in output

    def test_renders_additional_status_fields(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vs = VehicleState(
            locked=False,
            center_display_state=2,
            remote_start_enabled=True,
            is_user_present=True,
            homelink_nearby=True,
        )
        ro.vehicle_status(vs)
        output = buf.getvalue()

        assert "Center display" in output
        assert "on" in output
        assert "Remote start" in output
        assert "User present" in output
        assert "Homelink" in output


class TestVehicleConfig:
    def test_renders_extended_config_fields(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vc = VehicleConfig(
            car_type="modely",
            roof_color="Glass",
            can_actuate_trunks=True,
            plg=True,
            eu_vehicle=True,
        )
        ro.vehicle_config(vc)
        output = buf.getvalue()

        assert "modely" in output
        assert "Glass" in output
        assert "Trunk actuation" in output
        assert "Power liftgate" in output
        assert "EU vehicle" in output


class TestGuiSettings:
    def test_renders_units(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        gs = GuiSettings(gui_distance_units="mi/hr", gui_temperature_units="F")
        ro.gui_settings(gs)
        output = buf.getvalue()

        assert "mi/hr" in output
        assert "F" in output
        assert "Display Settings" in output

    def test_vehicle_data_includes_gui_settings(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console)

        vd = VehicleData(
            vin="5YJ3E1EA1NF000001",
            gui_settings=GuiSettings(
                gui_distance_units="km/hr",
                gui_temperature_units="C",
                gui_charge_rate_units="kW",
            ),
        )
        ro.vehicle_data(vd)
        output = buf.getvalue()

        assert "Display Settings" in output
        assert "km/hr" in output


class TestMetricUnits:
    """Verify non-default (metric) unit conversions."""

    _METRIC = DisplayUnits(
        pressure=PressureUnit.BAR,
        temp=TempUnit.C,
        distance=DistanceUnit.KM,
    )

    def test_temperature_in_celsius(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console, units=self._METRIC)

        cs = ClimateState(inside_temp=22.0, outside_temp=15.5)
        ro.climate_status(cs)
        output = buf.getvalue()

        assert "22.0\u00b0C" in output
        assert "15.5\u00b0C" in output

    def test_distance_in_km(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console, units=self._METRIC)

        cs = ChargeState(battery_range=250.0, charge_rate=30.0)
        ro.charge_status(cs)
        output = buf.getvalue()

        # 250 mi → 402.3 km, 30 mi/hr → 48.3 km/hr
        assert "402.3" in output
        assert "km" in output
        assert "48.3" in output

    def test_location_does_not_show_speed(self) -> None:
        """Location display shows GPS fields only, not drive dynamics."""
        console, buf = _make_console()
        ro = RichOutput(console, units=self._METRIC)

        ds = DriveState(latitude=37.394, longitude=-122.150, speed=60)
        ro.location(ds)
        output = buf.getvalue()

        assert "37.394" in output
        # Speed is a drive_state field, not shown in location
        assert "km/h" not in output

    def test_pressure_in_bar(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console, units=self._METRIC)

        vs = VehicleState(locked=True, tpms_pressure_fl=2.90, tpms_pressure_fr=3.00)
        ro.vehicle_status(vs)
        output = buf.getvalue()

        assert "2.90" in output
        assert "3.00" in output
        assert "bar" in output

    def test_odometer_in_km(self) -> None:
        console, buf = _make_console()
        ro = RichOutput(console, units=self._METRIC)

        vs = VehicleState(locked=True, odometer=50000.0)
        ro.vehicle_status(vs)
        output = buf.getvalue()

        # 50000 mi → 80,467.0 km
        assert "80,467.0" in output
        assert "km" in output


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
