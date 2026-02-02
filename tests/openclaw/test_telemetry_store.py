"""Tests for TelemetryStore in-memory latest-values cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tescmd.openclaw.telemetry_store import FieldSnapshot, TelemetryStore


class TestFieldSnapshot:
    def test_slots(self) -> None:
        snap = FieldSnapshot(value=42, timestamp=datetime(2026, 1, 1, tzinfo=UTC))
        assert snap.value == 42
        assert snap.timestamp.year == 2026


class TestTelemetryStoreUpdateGet:
    def test_update_and_get_roundtrip(self) -> None:
        store = TelemetryStore()
        ts = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
        store.update("Soc", 72.0, ts)
        snap = store.get("Soc")
        assert snap is not None
        assert snap.value == 72.0
        assert snap.timestamp == ts

    def test_get_returns_none_for_missing(self) -> None:
        store = TelemetryStore()
        assert store.get("NonExistent") is None

    def test_update_overwrites_previous(self) -> None:
        store = TelemetryStore()
        ts1 = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 1, 31, 12, 1, 0, tzinfo=UTC)
        store.update("Soc", 50.0, ts1)
        store.update("Soc", 72.0, ts2)
        snap = store.get("Soc")
        assert snap is not None
        assert snap.value == 72.0
        assert snap.timestamp == ts2

    def test_update_multiple_fields(self) -> None:
        store = TelemetryStore()
        ts = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
        store.update("Soc", 72.0, ts)
        store.update("Locked", True, ts)
        assert store.get("Soc") is not None
        assert store.get("Locked") is not None
        assert store.get("Soc").value == 72.0  # type: ignore[union-attr]
        assert store.get("Locked").value is True  # type: ignore[union-attr]

    def test_stores_complex_values(self) -> None:
        store = TelemetryStore()
        ts = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
        loc = {"latitude": 37.7749, "longitude": -122.4194}
        store.update("Location", loc, ts)
        snap = store.get("Location")
        assert snap is not None
        assert snap.value == loc


class TestTelemetryStoreGetAll:
    def test_get_all_empty(self) -> None:
        store = TelemetryStore()
        assert store.get_all() == {}

    def test_get_all_returns_all_fields(self) -> None:
        store = TelemetryStore()
        ts = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
        store.update("Soc", 72.0, ts)
        store.update("Locked", True, ts)
        store.update("VehicleSpeed", 65.0, ts)
        result = store.get_all()
        assert len(result) == 3
        assert "Soc" in result
        assert "Locked" in result
        assert "VehicleSpeed" in result

    def test_get_all_returns_copy(self) -> None:
        store = TelemetryStore()
        ts = datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC)
        store.update("Soc", 72.0, ts)
        copy = store.get_all()
        copy["Extra"] = FieldSnapshot(value=1, timestamp=ts)
        assert store.get("Extra") is None


class TestTelemetryStoreAge:
    def test_age_seconds_returns_none_for_missing(self) -> None:
        store = TelemetryStore()
        assert store.age_seconds("Soc") is None

    def test_age_seconds_returns_positive(self) -> None:
        store = TelemetryStore()
        old = datetime.now(UTC) - timedelta(seconds=30)
        store.update("Soc", 72.0, old)
        age = store.age_seconds("Soc")
        assert age is not None
        assert age >= 29.0  # allow 1s tolerance

    def test_age_seconds_recent_is_small(self) -> None:
        store = TelemetryStore()
        store.update("Soc", 72.0, datetime.now(UTC))
        age = store.age_seconds("Soc")
        assert age is not None
        assert age < 2.0
