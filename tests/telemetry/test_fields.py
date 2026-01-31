"""Tests for telemetry field registry and presets."""

from __future__ import annotations

import pytest

from tescmd.api.errors import ConfigError
from tescmd.telemetry.fields import FIELD_NAMES, resolve_fields


class TestFieldNames:
    def test_has_core_fields(self) -> None:
        assert FIELD_NAMES[3] == "Soc"
        assert FIELD_NAMES[4] == "VehicleSpeed"
        assert FIELD_NAMES[8] == "BatteryLevel"
        assert FIELD_NAMES[9] == "Location"
        assert FIELD_NAMES[33] == "InsideTemp"

    def test_has_many_fields(self) -> None:
        assert len(FIELD_NAMES) >= 100


class TestPresets:
    def test_default_preset(self) -> None:
        fields = resolve_fields("default")
        assert "Soc" in fields
        assert "VehicleSpeed" in fields
        assert fields["Soc"]["interval_seconds"] == 10
        assert fields["VehicleSpeed"]["interval_seconds"] == 1

    def test_driving_preset(self) -> None:
        fields = resolve_fields("driving")
        assert "VehicleSpeed" in fields
        assert "Location" in fields
        assert "Heading" in fields

    def test_charging_preset(self) -> None:
        fields = resolve_fields("charging")
        assert "Soc" in fields
        assert "PackVoltage" in fields
        assert "ChargerActualCurrent" in fields

    def test_climate_preset(self) -> None:
        fields = resolve_fields("climate")
        assert "InsideTemp" in fields
        assert "OutsideTemp" in fields

    def test_all_preset(self) -> None:
        fields = resolve_fields("all")
        assert len(fields) == len(FIELD_NAMES)


class TestResolveFields:
    def test_comma_separated(self) -> None:
        fields = resolve_fields("Soc,VehicleSpeed,BatteryLevel")
        assert set(fields.keys()) == {"Soc", "VehicleSpeed", "BatteryLevel"}

    def test_interval_override(self) -> None:
        fields = resolve_fields("default", interval_override=5)
        for _name, config in fields.items():
            assert config["interval_seconds"] == 5

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown telemetry field"):
            resolve_fields("Soc,NonExistentField")

    def test_single_field(self) -> None:
        fields = resolve_fields("Soc")
        assert "Soc" in fields

    def test_whitespace_handling(self) -> None:
        fields = resolve_fields(" Soc , VehicleSpeed ")
        assert set(fields.keys()) == {"Soc", "VehicleSpeed"}
