"""Tests for the TelemetryMapper field mapping."""

from __future__ import annotations

import pytest

from tescmd.telemetry.mapper import (
    FieldMapping,
    TelemetryMapper,
    _extract_lat,
    _extract_lon,
    _gear_str,
    _to_bool,
    _to_float,
    _to_int,
    _to_str,
)

# ---------------------------------------------------------------------------
# Transform function tests
# ---------------------------------------------------------------------------


class TestTransforms:
    def test_to_int(self) -> None:
        assert _to_int(42) == 42
        assert _to_int(3.7) == 3
        assert _to_int("10") == 10
        assert _to_int(None) is None
        assert _to_int("abc") is None

    def test_to_float(self) -> None:
        assert _to_float(3.14) == 3.14
        assert _to_float(10) == 10.0
        assert _to_float("2.5") == 2.5
        assert _to_float(None) is None
        assert _to_float("abc") is None

    def test_to_bool(self) -> None:
        assert _to_bool(True) is True
        assert _to_bool(False) is False
        assert _to_bool(1) is True
        assert _to_bool(0) is False
        assert _to_bool("true") is True
        assert _to_bool("false") is False
        assert _to_bool("yes") is True
        assert _to_bool(None) is None

    def test_to_str(self) -> None:
        assert _to_str("hello") == "hello"
        assert _to_str(42) == "42"
        assert _to_str(None) is None

    def test_extract_lat(self) -> None:
        assert _extract_lat({"latitude": 37.7749, "longitude": -122.4194}) == 37.7749
        assert _extract_lat({"longitude": -122.4194}) is None
        assert _extract_lat("not a dict") is None
        assert _extract_lat(None) is None

    def test_extract_lon(self) -> None:
        assert _extract_lon({"latitude": 37.7749, "longitude": -122.4194}) == -122.4194
        assert _extract_lon({"latitude": 37.7749}) is None

    def test_gear_str(self) -> None:
        assert _gear_str("P") == "P"
        assert _gear_str("Park") == "P"
        assert _gear_str("D") == "D"
        assert _gear_str("Drive") == "D"
        assert _gear_str("R") == "R"
        assert _gear_str("Reverse") == "R"
        assert _gear_str("N") == "N"
        assert _gear_str("Neutral") == "N"
        assert _gear_str("Unknown") == "Unknown"
        assert _gear_str(None) is None


# ---------------------------------------------------------------------------
# TelemetryMapper tests
# ---------------------------------------------------------------------------


class TestTelemetryMapper:
    def test_map_simple_field(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("Soc", 80)
        assert len(results) == 1
        assert results[0] == ("charge_state.usable_battery_level", 80)

    def test_map_battery_level(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("BatteryLevel", 75)
        assert results == [("charge_state.battery_level", 75)]

    def test_map_location_produces_two_paths(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("Location", {"latitude": 37.7749, "longitude": -122.4194})
        assert len(results) == 2
        paths = {r[0] for r in results}
        assert paths == {"drive_state.latitude", "drive_state.longitude"}
        values = {r[0]: r[1] for r in results}
        assert values["drive_state.latitude"] == pytest.approx(37.7749)
        assert values["drive_state.longitude"] == pytest.approx(-122.4194)

    def test_map_location_missing_fields(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("Location", {"latitude": 37.7})
        assert len(results) == 1
        assert results[0][0] == "drive_state.latitude"

    def test_map_unmapped_field(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("UnknownField123", 42)
        assert results == []

    def test_map_inside_temp(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("InsideTemp", 22.5)
        assert results == [("climate_state.inside_temp", 22.5)]

    def test_map_locked(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("Locked", True)
        assert results == [("vehicle_state.locked", True)]

    def test_map_gear(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("Gear", "Drive")
        assert results == [("drive_state.shift_state", "D")]

    def test_map_charge_state(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("ChargeState", "Charging")
        assert results == [("charge_state.charging_state", "Charging")]

    def test_map_speed(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("VehicleSpeed", 65)
        assert results == [("drive_state.speed", 65)]

    def test_map_odometer(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("Odometer", 12345.6)
        assert results == [("vehicle_state.odometer", 12345.6)]

    def test_map_version(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("Version", "2024.26.3.1")
        assert results == [("vehicle_state.car_version", "2024.26.3.1")]

    def test_mapped_fields_property(self) -> None:
        mapper = TelemetryMapper()
        fields = mapper.mapped_fields
        assert "Soc" in fields
        assert "Location" in fields
        assert "BatteryLevel" in fields
        assert "InsideTemp" in fields
        assert "Locked" in fields

    def test_custom_field_map(self) -> None:
        custom_map = {
            "CustomField": [FieldMapping("custom.path", _to_int)],
        }
        mapper = TelemetryMapper(field_map=custom_map)
        results = mapper.map("CustomField", "42")
        assert results == [("custom.path", 42)]
        assert mapper.map("Soc", 80) == []

    def test_transform_returning_none_is_excluded(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("VehicleSpeed", "not-a-number")
        assert results == []

    def test_tpms_pressures(self) -> None:
        mapper = TelemetryMapper()
        for field, path in [
            ("TpmsPressureFl", "vehicle_state.tpms_pressure_fl"),
            ("TpmsPressureFr", "vehicle_state.tpms_pressure_fr"),
            ("TpmsPressureRl", "vehicle_state.tpms_pressure_rl"),
            ("TpmsPressureRr", "vehicle_state.tpms_pressure_rr"),
        ]:
            results = mapper.map(field, 2.8)
            assert results == [(path, 2.8)], f"Failed for {field}"

    def test_charge_limit_soc(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("ChargeLimitSoc", 80)
        assert results == [("charge_state.charge_limit_soc", 80)]

    def test_est_battery_range(self) -> None:
        mapper = TelemetryMapper()
        results = mapper.map("EstBatteryRange", 210.5)
        assert results == [("charge_state.est_battery_range", 210.5)]
