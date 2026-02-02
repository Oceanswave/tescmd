"""Tests for telemetry field registry and presets."""

from __future__ import annotations

import pytest

from tescmd.api.errors import ConfigError
from tescmd.telemetry.fields import FIELD_NAMES, resolve_fields


class TestFieldNames:
    def test_has_core_fields(self) -> None:
        # IDs match the actual vehicle_data.proto Field enum.
        assert FIELD_NAMES[8] == "Soc"
        assert FIELD_NAMES[4] == "VehicleSpeed"
        assert FIELD_NAMES[42] == "BatteryLevel"
        assert FIELD_NAMES[21] == "Location"
        assert FIELD_NAMES[85] == "InsideTemp"

    def test_has_many_fields(self) -> None:
        assert len(FIELD_NAMES) >= 200


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
        assert "GpsHeading" in fields

    def test_charging_preset(self) -> None:
        fields = resolve_fields("charging")
        assert "Soc" in fields
        assert "PackVoltage" in fields
        assert "ChargeAmps" in fields

    def test_climate_preset(self) -> None:
        fields = resolve_fields("climate")
        assert "InsideTemp" in fields
        assert "OutsideTemp" in fields
        assert "HvacPower" in fields

    def test_all_preset(self) -> None:
        fields = resolve_fields("all")
        from tescmd.telemetry.fields import _NON_STREAMABLE_FIELDS

        assert len(fields) == len(FIELD_NAMES) - len(_NON_STREAMABLE_FIELDS)
        for excluded in _NON_STREAMABLE_FIELDS:
            assert excluded not in fields

    def test_all_preset_excludes_semitruck(self) -> None:
        fields = resolve_fields("all")
        for name in fields:
            assert not name.startswith("Semitruck"), f"Semi-truck field in all preset: {name}"

    def test_all_preset_delta_fields_have_both_keys(self) -> None:
        """Delta fields must have both interval_seconds and minimum_delta."""
        from tescmd.telemetry.fields import _DELTA_FIELDS

        fields = resolve_fields("all")
        for name in _DELTA_FIELDS:
            assert name in fields, f"Delta field {name} missing from all preset"
            config = fields[name]
            assert "interval_seconds" in config, f"{name} missing interval_seconds"
            assert "minimum_delta" in config, f"{name} missing minimum_delta"
            assert config["minimum_delta"] >= 1, f"{name} minimum_delta must be >= 1"

    def test_presets_use_valid_field_names(self) -> None:
        """Every field name in every preset must exist in FIELD_NAMES."""
        from tescmd.telemetry.fields import PRESETS

        valid_names = set(FIELD_NAMES.values())
        for preset_name, preset_fields in PRESETS.items():
            for field_name in preset_fields:
                assert field_name in valid_names, (
                    f"Preset '{preset_name}' references unknown field '{field_name}'"
                )


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

    def test_old_rest_api_names_rejected(self) -> None:
        """Old REST API names that don't match proto should be rejected."""
        old_names = [
            "DriveState",
            "RatedBatteryRange",
            "ChargerActualCurrent",
            "ChargerPilotCurrent",
        ]
        for name in old_names:
            with pytest.raises(ConfigError, match="Unknown telemetry field"):
                resolve_fields(name)

    def test_single_field(self) -> None:
        fields = resolve_fields("Soc")
        assert "Soc" in fields

    def test_whitespace_handling(self) -> None:
        fields = resolve_fields(" Soc , VehicleSpeed ")
        assert set(fields.keys()) == {"Soc", "VehicleSpeed"}
