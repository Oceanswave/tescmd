"""Tests for EventEmitter telemetry-to-OpenClaw event mapping."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tescmd.openclaw.emitter import EventEmitter


@pytest.fixture()
def emitter() -> EventEmitter:
    return EventEmitter(client_id="test-bridge")


class TestLocationEvent:
    def test_valid_location(self, emitter: EventEmitter) -> None:
        event = emitter.to_event(
            "Location",
            {"latitude": 40.7128, "longitude": -74.006, "heading": 90.0, "speed": 30.0},
            vin="VIN1",
        )
        assert event is not None
        assert event["method"] == "req:agent"
        params = event["params"]
        assert params["event_type"] == "location"
        assert params["vin"] == "VIN1"
        assert params["data"]["latitude"] == 40.7128
        assert params["data"]["longitude"] == -74.006
        assert params["data"]["heading"] == 90.0
        assert params["data"]["speed"] == 30.0

    def test_location_missing_optional_fields(self, emitter: EventEmitter) -> None:
        event = emitter.to_event(
            "Location",
            {"latitude": 40.0, "longitude": -74.0},
            vin="VIN1",
        )
        assert event is not None
        assert event["params"]["data"]["heading"] == 0
        assert event["params"]["data"]["speed"] == 0

    def test_invalid_location_returns_none(self, emitter: EventEmitter) -> None:
        assert emitter.to_event("Location", "bad", vin="VIN1") is None
        assert emitter.to_event("Location", {}, vin="VIN1") is None


class TestBatteryEvents:
    def test_soc_event(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("Soc", 72.5, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "battery"
        assert event["params"]["data"]["battery_level"] == 72.5

    def test_battery_level_event(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("BatteryLevel", 85, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "battery"
        assert event["params"]["data"]["battery_level"] == 85.0

    def test_range_event(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("EstBatteryRange", 250.5, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "battery"
        assert event["params"]["data"]["range_miles"] == 250.5

    def test_invalid_soc_returns_none(self, emitter: EventEmitter) -> None:
        assert emitter.to_event("Soc", "bad", vin="VIN1") is None


class TestTempEvents:
    def test_inside_temp(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("InsideTemp", 22.0, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "inside_temp"
        # 22C = 71.6F
        assert event["params"]["data"]["inside_temp_f"] == 71.6

    def test_outside_temp(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("OutsideTemp", 0.0, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "outside_temp"
        # 0C = 32F
        assert event["params"]["data"]["outside_temp_f"] == 32.0

    def test_invalid_temp_returns_none(self, emitter: EventEmitter) -> None:
        assert emitter.to_event("InsideTemp", "hot", vin="VIN1") is None


class TestSpeedEvent:
    def test_speed(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("VehicleSpeed", 65.0, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "speed"
        assert event["params"]["data"]["speed_mph"] == 65.0


class TestChargeStateEvents:
    def test_charging_state(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("ChargeState", "Charging", vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "charge_started"
        assert event["params"]["data"]["state"] == "Charging"

    def test_complete_state(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("ChargeState", "Complete", vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "charge_complete"

    def test_stopped_state(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("ChargeState", "Stopped", vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "charge_stopped"

    def test_disconnected_state(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("ChargeState", "Disconnected", vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "charge_stopped"

    def test_detailed_charge_state(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("DetailedChargeState", "Starting", vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "charge_started"


class TestSecurityEvents:
    def test_locked(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("Locked", True, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "security_changed"
        assert event["params"]["data"]["field"] == "locked"
        assert event["params"]["data"]["value"] is True

    def test_sentry_mode(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("SentryMode", False, vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "security_changed"
        assert event["params"]["data"]["field"] == "sentrymode"


class TestGearEvent:
    def test_gear(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("Gear", "D", vin="VIN1")
        assert event is not None
        assert event["params"]["event_type"] == "gear_changed"
        assert event["params"]["data"]["gear"] == "D"


class TestUnmappedField:
    def test_unknown_field_returns_none(self, emitter: EventEmitter) -> None:
        assert emitter.to_event("UnknownField", 42, vin="VIN1") is None


class TestTimestamp:
    def test_custom_timestamp(self, emitter: EventEmitter) -> None:
        ts = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
        event = emitter.to_event("Soc", 72, vin="VIN1", timestamp=ts)
        assert event is not None
        assert event["params"]["timestamp"] == "2026-01-31T12:00:00+00:00"

    def test_source_matches_client_id(self, emitter: EventEmitter) -> None:
        event = emitter.to_event("Soc", 72, vin="VIN1")
        assert event is not None
        assert event["params"]["source"] == "test-bridge"
