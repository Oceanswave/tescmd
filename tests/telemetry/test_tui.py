"""Tests for the TelemetryTUI Textual dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest
from textual.widgets import DataTable, Static

from tescmd.telemetry.decoder import TelemetryDatum, TelemetryFrame
from tescmd.telemetry.tui import (
    PANEL_FIELDS,
    HelpScreen,
    TelemetryTUI,
    _format_value,
    _mask_vin,
)

VIN = "5YJ3E1EA0KF000001"


def _frame(
    *fields: tuple[str, int, Any, str],
    vin: str = VIN,
    ts: datetime | None = None,
) -> TelemetryFrame:
    return TelemetryFrame(
        vin=vin,
        created_at=ts or datetime.now(UTC),
        data=[
            TelemetryDatum(field_name=name, field_id=fid, value=val, value_type=vtype)
            for name, fid, val, vtype in fields
        ],
    )


# ---------------------------------------------------------------------------
# _format_value (unit-free)
# ---------------------------------------------------------------------------


class TestFormatValueNoUnits:
    def test_none_value(self) -> None:
        assert _format_value("Anything", None, None) == "\u2014"

    def test_bool_true(self) -> None:
        assert _format_value("Locked", True, None) == "Yes"

    def test_bool_false(self) -> None:
        assert _format_value("Locked", False, None) == "No"

    def test_float_value(self) -> None:
        assert _format_value("SomeFloat", 3.14159, None) == "3.14"

    def test_int_value(self) -> None:
        assert _format_value("SomeInt", 42, None) == "42"

    def test_string_value(self) -> None:
        assert _format_value("SomeStr", "hello", None) == "hello"

    def test_location_dict(self) -> None:
        result = _format_value("Location", {"latitude": 37.77, "longitude": -122.42}, None)
        assert "37.77" in result
        assert "-122.42" in result


# ---------------------------------------------------------------------------
# _format_value (with units)
# ---------------------------------------------------------------------------


class TestFormatValueWithUnits:
    @pytest.fixture
    def units_imperial(self) -> Any:
        """Return DisplayUnits with imperial settings."""
        from tescmd.output.rich_output import DisplayUnits, DistanceUnit, PressureUnit, TempUnit

        return DisplayUnits(temp=TempUnit.F, distance=DistanceUnit.MI, pressure=PressureUnit.PSI)

    @pytest.fixture
    def units_metric(self) -> Any:
        from tescmd.output.rich_output import DisplayUnits, DistanceUnit, PressureUnit, TempUnit

        return DisplayUnits(temp=TempUnit.C, distance=DistanceUnit.KM, pressure=PressureUnit.BAR)

    def test_temp_fahrenheit(self, units_imperial: Any) -> None:
        result = _format_value("InsideTemp", 22.5, units_imperial)
        assert "\u00b0F" in result
        assert "72.5" in result

    def test_temp_celsius(self, units_metric: Any) -> None:
        result = _format_value("InsideTemp", 22.5, units_metric)
        assert "\u00b0C" in result

    def test_distance_km(self, units_metric: Any) -> None:
        result = _format_value("Odometer", 100.0, units_metric)
        assert "km" in result

    def test_distance_mi(self, units_imperial: Any) -> None:
        result = _format_value("Odometer", 100.0, units_imperial)
        assert "mi" in result

    def test_speed_kmh(self, units_metric: Any) -> None:
        result = _format_value("VehicleSpeed", 60, units_metric)
        assert "km/h" in result

    def test_speed_mph(self, units_imperial: Any) -> None:
        result = _format_value("VehicleSpeed", 60, units_imperial)
        assert "mph" in result

    def test_pressure_psi(self, units_imperial: Any) -> None:
        result = _format_value("TpmsPressureFl", 2.5, units_imperial)
        assert "psi" in result

    def test_pressure_bar(self, units_metric: Any) -> None:
        result = _format_value("TpmsPressureFl", 2.5, units_metric)
        assert "bar" in result

    def test_percentage(self, units_imperial: Any) -> None:
        result = _format_value("BatteryLevel", 80, units_imperial)
        assert "80%" in result

    def test_voltage(self, units_imperial: Any) -> None:
        result = _format_value("PackVoltage", 400.5, units_imperial)
        assert "V" in result

    def test_current(self, units_imperial: Any) -> None:
        result = _format_value("PackCurrent", 12.5, units_imperial)
        assert "A" in result

    def test_power(self, units_imperial: Any) -> None:
        result = _format_value("BatteryPower", 7.5, units_imperial)
        assert "kW" in result

    def test_time_to_full(self, units_imperial: Any) -> None:
        result = _format_value("TimeToFullCharge", 1.5, units_imperial)
        assert "1h 30m" in result

    def test_time_to_full_minutes_only(self, units_imperial: Any) -> None:
        result = _format_value("TimeToFullCharge", 0.5, units_imperial)
        assert "30m" in result
        assert "h" not in result


# ---------------------------------------------------------------------------
# _mask_vin
# ---------------------------------------------------------------------------


class TestVinMasking:
    def test_normal_vin(self) -> None:
        assert _mask_vin("5YJ3E1EA0KF000001") == "5YJ3E1EA0KF00XXXX"

    def test_short_vin(self) -> None:
        assert _mask_vin("ABCD") == "XXXX"

    def test_very_short_vin(self) -> None:
        # Fewer than 4 chars — returned as-is.
        assert _mask_vin("AB") == "AB"

    def test_empty_vin(self) -> None:
        assert _mask_vin("") == ""


# ---------------------------------------------------------------------------
# PANEL_FIELDS mapping
# ---------------------------------------------------------------------------


class TestPanelFieldMapping:
    def test_common_fields_covered(self) -> None:
        """Well-known telemetry fields should be in a panel."""
        from tescmd.telemetry.tui import _FIELD_TO_PANEL

        for field in ("BatteryLevel", "InsideTemp", "VehicleSpeed", "Locked", "TpmsPressureFl"):
            assert field in _FIELD_TO_PANEL, f"{field} not mapped to any panel"

    def test_no_duplicates_across_panels(self) -> None:
        """Each field should appear in exactly one panel."""
        seen: dict[str, str] = {}
        for panel_id, (_title, fields) in PANEL_FIELDS.items():
            for f in fields:
                assert f not in seen, f"{f} in both {seen[f]} and {panel_id}"
                seen[f] = panel_id

    def test_all_panels_have_title(self) -> None:
        for panel_id, (title, _fields) in PANEL_FIELDS.items():
            assert title, f"Panel {panel_id} has empty title"

    def test_all_panels_have_fields(self) -> None:
        for panel_id, (_title, fields) in PANEL_FIELDS.items():
            assert len(fields) > 0, f"Panel {panel_id} has no fields"


# ---------------------------------------------------------------------------
# TelemetryTUI — app lifecycle and frame processing
# ---------------------------------------------------------------------------


class TestTelemetryTUIApp:
    @pytest.mark.asyncio
    async def test_app_starts_and_stops(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            # App should be running.
            assert app.is_running
            # Press q to quit.
            await pilot.press("q")

    @pytest.mark.asyncio
    async def test_quit_signals_shutdown_event(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            assert not app.shutdown_event.is_set()
            await pilot.press("q")
            assert app.shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_header_shows_masked_vin(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._update_header()
            title = app.title or ""
            # Should show masked VIN (last 4 replaced with XXXX).
            assert "XXXX" in title
            # Should NOT show the full real VIN.
            assert VIN not in title

    @pytest.mark.asyncio
    async def test_header_shows_connection_status(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._update_header()
            assert "Waiting" in (app.title or "")
            app._connected = True
            app._update_header()
            assert "Connected" in (app.title or "")

    @pytest.mark.asyncio
    async def test_push_frame_updates_state(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            frame = _frame(("BatteryLevel", 8, 80, "int"))
            await app.push_frame(frame)

            import asyncio

            # Give the worker time to pick up the frame.
            for _ in range(20):
                if "BatteryLevel" in app._state:
                    break
                await asyncio.sleep(0.05)

            assert "BatteryLevel" in app._state
            assert app._state["BatteryLevel"] == 80

    @pytest.mark.asyncio
    async def test_battery_field_in_battery_table(self) -> None:
        """BatteryLevel should appear in the battery panel's DataTable."""
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._state["BatteryLevel"] = 80
            app._timestamps["BatteryLevel"] = datetime.now(UTC)
            app._update_panels()

            table = app.query_one("#battery-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_climate_field_in_climate_table(self) -> None:
        """InsideTemp should appear in the climate panel's DataTable."""
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._state["InsideTemp"] = 22.5
            app._timestamps["InsideTemp"] = datetime.now(UTC)
            app._update_panels()

            table = app.query_one("#climate-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_security_field_in_security_table(self) -> None:
        """Locked should appear in the security panel's DataTable."""
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._state["Locked"] = True
            app._timestamps["Locked"] = datetime.now(UTC)
            app._update_panels()

            table = app.query_one("#security-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_unknown_field_goes_to_diagnostics(self) -> None:
        """Fields not in any panel should fall through to diagnostics."""
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._state["UnknownField123"] = 42
            app._timestamps["UnknownField123"] = datetime.now(UTC)
            app._update_panels()

            table = app.query_one("#diagnostics-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    async def test_queue_overflow_drops_silently(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            # Fill the queue.
            for i in range(110):
                await app.push_frame(_frame(("BatteryLevel", 8, 80 - i, "int")))

            # No exception should be raised — overflow is silent.
            assert app._queue.qsize() <= 100

    @pytest.mark.asyncio
    async def test_server_info_setters(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app.set_mcp_url("http://127.0.0.1:8080/mcp")
            app.set_tunnel_url("https://tesla-abc.ts.net")
            app.set_sink_count(3)
            app.set_openclaw_status(True, 100, 95)
            app.set_cache_stats(500, 3000, 5)
            app.set_log_path("/tmp/test.csv")

            app._update_server_info()

            assert app._mcp_url == "http://127.0.0.1:8080/mcp"
            assert app._tunnel_url == "https://tesla-abc.ts.net"
            assert app._sink_count == 3
            assert "Connected" in app._openclaw_status

            info = app.query_one("#server-bar", Static)
            assert info.display is True

    @pytest.mark.asyncio
    async def test_server_info_hidden_when_empty(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._update_server_info()
            info = app.query_one("#server-bar", Static)
            assert info.display is False

    @pytest.mark.asyncio
    async def test_new_field_adds_table_row(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._state["BatteryLevel"] = 80
            app._timestamps["BatteryLevel"] = datetime.now(UTC)
            app._update_panels()

            table = app.query_one("#battery-table", DataTable)
            assert table.row_count == 1

            # Second field in same panel.
            app._state["Soc"] = 80
            app._timestamps["Soc"] = datetime.now(UTC)
            app._update_panels()

            assert table.row_count == 2

    @pytest.mark.asyncio
    async def test_existing_field_updates_in_place(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._state["BatteryLevel"] = 80
            app._timestamps["BatteryLevel"] = datetime.now(UTC)
            app._update_panels()

            table = app.query_one("#battery-table", DataTable)
            assert table.row_count == 1

            # Update same field.
            app._state["BatteryLevel"] = 75
            app._update_panels()

            # Still one row, not two.
            assert table.row_count == 1


# ---------------------------------------------------------------------------
# Keybindings
# ---------------------------------------------------------------------------


class TestKeybindings:
    @pytest.mark.asyncio
    async def test_lock_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("l")
                mock.assert_called_once_with(["security", "lock"], "Lock doors")

    @pytest.mark.asyncio
    async def test_unlock_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("u")
                mock.assert_called_once_with(["security", "unlock"], "Unlock doors")

    @pytest.mark.asyncio
    async def test_honk_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("h")
                mock.assert_called_once_with(["security", "honk"], "Honk horn")

    @pytest.mark.asyncio
    async def test_flash_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("f")
                mock.assert_called_once_with(["security", "flash"], "Flash lights")

    @pytest.mark.asyncio
    async def test_charge_start_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("c")
                mock.assert_called_once_with(["charge", "start"], "Start charging")

    @pytest.mark.asyncio
    async def test_climate_on_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("a")
                mock.assert_called_once_with(["climate", "on"], "Climate on")

    @pytest.mark.asyncio
    async def test_trunk_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("t")
                mock.assert_called_once_with(["trunk", "open"], "Trunk open/close")

    @pytest.mark.asyncio
    async def test_play_pause_keybinding(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            with patch.object(app, "_run_command") as mock:
                await pilot.press("space")
                mock.assert_called_once_with(["media", "play-pause"], "Play/Pause")


# ---------------------------------------------------------------------------
# Command status bar
# ---------------------------------------------------------------------------


class TestCommandStatus:
    @pytest.mark.asyncio
    async def test_command_status_shows_on_send(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._show_command_status("Sending: Lock doors...")
            widget = app.query_one("#command-status", Static)
            assert widget.display is True

    @pytest.mark.asyncio
    async def test_command_status_hides(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._show_command_status("OK: Lock doors")
            app._hide_command_status()
            widget = app.query_one("#command-status", Static)
            assert widget.display is False


# ---------------------------------------------------------------------------
# Help screen
# ---------------------------------------------------------------------------


class TestHelpScreen:
    @pytest.mark.asyncio
    async def test_help_screen_pushes(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            # The HelpScreen should now be the active screen.
            assert isinstance(app.screen, HelpScreen)

    @pytest.mark.asyncio
    async def test_help_screen_dismissed_with_escape(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            # Should return to the default screen.
            assert not isinstance(app.screen, HelpScreen)

    @pytest.mark.asyncio
    async def test_help_screen_shows_log_path(self) -> None:
        app = TelemetryTUI(vin=VIN)
        app.set_log_path("/tmp/telemetry.csv")
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            screen = app.screen
            assert isinstance(screen, HelpScreen)
            # Should include the CSV log path in the combined log_path field.
            assert "/tmp/telemetry.csv" in screen._log_path


# ---------------------------------------------------------------------------
# Header subtitle
# ---------------------------------------------------------------------------


class TestHeaderSubtitle:
    @pytest.mark.asyncio
    async def test_subtitle_contains_frame_count(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._frame_count = 42
            app._update_header()
            assert "42" in (app.sub_title or "")

    @pytest.mark.asyncio
    async def test_subtitle_contains_uptime(self) -> None:
        app = TelemetryTUI(vin=VIN)
        async with app.run_test():
            app._update_header()
            sub = app.sub_title or ""
            assert "Up:" in sub
            # Should have HH:MM:SS format.
            assert "00:" in sub
