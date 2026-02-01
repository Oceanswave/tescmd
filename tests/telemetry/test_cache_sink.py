"""Tests for the CacheSink telemetry-to-cache pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from tescmd.cache.response_cache import ResponseCache
from tescmd.telemetry.cache_sink import CacheSink, _deep_merge, _deep_set
from tescmd.telemetry.decoder import TelemetryDatum, TelemetryFrame
from tescmd.telemetry.mapper import TelemetryMapper

if TYPE_CHECKING:
    from pathlib import Path

VIN = "5YJ3E1EA0KF000001"


@pytest.fixture
def cache(tmp_path: Path) -> ResponseCache:
    return ResponseCache(cache_dir=tmp_path, default_ttl=60, enabled=True)


@pytest.fixture
def mapper() -> TelemetryMapper:
    return TelemetryMapper()


@pytest.fixture
def sink(cache: ResponseCache, mapper: TelemetryMapper) -> CacheSink:
    return CacheSink(cache, mapper, VIN, flush_interval=0.0)


def _frame(
    *fields: tuple[str, int, Any, str],
    vin: str = VIN,
) -> TelemetryFrame:
    return TelemetryFrame(
        vin=vin,
        created_at=datetime.now(UTC),
        data=[
            TelemetryDatum(field_name=name, field_id=fid, value=val, value_type=vtype)
            for name, fid, val, vtype in fields
        ],
    )


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestDeepSet:
    def test_simple_path(self) -> None:
        d: dict = {}
        _deep_set(d, "a.b.c", 42)
        assert d == {"a": {"b": {"c": 42}}}

    def test_single_key(self) -> None:
        d: dict = {}
        _deep_set(d, "x", 1)
        assert d == {"x": 1}

    def test_overwrite_existing(self) -> None:
        d: dict = {"a": {"b": 10}}
        _deep_set(d, "a.b", 20)
        assert d == {"a": {"b": 20}}

    def test_add_sibling(self) -> None:
        d: dict = {"a": {"b": 10}}
        _deep_set(d, "a.c", 20)
        assert d == {"a": {"b": 10, "c": 20}}

    def test_overwrite_non_dict(self) -> None:
        d: dict = {"a": "scalar"}
        _deep_set(d, "a.b", 42)
        assert d == {"a": {"b": 42}}


class TestDeepMerge:
    def test_simple_merge(self) -> None:
        base = {"a": 1}
        overlay = {"b": 2}
        _deep_merge(base, overlay)
        assert base == {"a": 1, "b": 2}

    def test_nested_merge(self) -> None:
        base = {"a": {"x": 1, "y": 2}}
        overlay = {"a": {"y": 3, "z": 4}}
        _deep_merge(base, overlay)
        assert base == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_overwrite_scalar(self) -> None:
        base = {"a": 1}
        overlay = {"a": 2}
        _deep_merge(base, overlay)
        assert base == {"a": 2}


# ---------------------------------------------------------------------------
# CacheSink tests
# ---------------------------------------------------------------------------


class TestCacheSink:
    @pytest.mark.asyncio
    async def test_single_field_flush(self, sink: CacheSink, cache: ResponseCache) -> None:
        frame = _frame(("Soc", 3, 80, "int"))
        await sink.on_frame(frame)
        sink.flush()

        result = cache.get(VIN)
        assert result is not None
        assert result.data["charge_state"]["usable_battery_level"] == 80

    @pytest.mark.asyncio
    async def test_multiple_fields_in_one_frame(
        self, sink: CacheSink, cache: ResponseCache
    ) -> None:
        frame = _frame(
            ("Soc", 3, 80, "int"),
            ("BatteryLevel", 8, 78, "int"),
            ("InsideTemp", 33, 22.5, "float"),
        )
        await sink.on_frame(frame)
        sink.flush()

        result = cache.get(VIN)
        assert result is not None
        assert result.data["charge_state"]["usable_battery_level"] == 80
        assert result.data["charge_state"]["battery_level"] == 78
        assert result.data["climate_state"]["inside_temp"] == 22.5

    @pytest.mark.asyncio
    async def test_incremental_merge(self, sink: CacheSink, cache: ResponseCache) -> None:
        frame1 = _frame(("Soc", 3, 80, "int"))
        await sink.on_frame(frame1)
        sink.flush()

        frame2 = _frame(("InsideTemp", 33, 23.0, "float"))
        await sink.on_frame(frame2)
        sink.flush()

        result = cache.get(VIN)
        assert result is not None
        assert result.data["charge_state"]["usable_battery_level"] == 80
        assert result.data["climate_state"]["inside_temp"] == 23.0

    @pytest.mark.asyncio
    async def test_updates_overwrite(self, sink: CacheSink, cache: ResponseCache) -> None:
        await sink.on_frame(_frame(("Soc", 3, 80, "int")))
        sink.flush()
        await sink.on_frame(_frame(("Soc", 3, 75, "int")))
        sink.flush()

        result = cache.get(VIN)
        assert result is not None
        assert result.data["charge_state"]["usable_battery_level"] == 75

    @pytest.mark.asyncio
    async def test_wrong_vin_ignored(self, sink: CacheSink, cache: ResponseCache) -> None:
        frame = _frame(("Soc", 3, 80, "int"), vin="OTHER_VIN_12345")
        await sink.on_frame(frame)
        sink.flush()

        assert cache.get(VIN) is None

    @pytest.mark.asyncio
    async def test_wake_state_set(self, sink: CacheSink, cache: ResponseCache) -> None:
        await sink.on_frame(_frame(("Soc", 3, 80, "int")))
        sink.flush()

        assert cache.get_wake_state(VIN) is True

    @pytest.mark.asyncio
    async def test_location_mapping(self, sink: CacheSink, cache: ResponseCache) -> None:
        frame = _frame(("Location", 9, {"latitude": 37.77, "longitude": -122.42}, "location"))
        await sink.on_frame(frame)
        sink.flush()

        result = cache.get(VIN)
        assert result is not None
        assert result.data["drive_state"]["latitude"] == pytest.approx(37.77)
        assert result.data["drive_state"]["longitude"] == pytest.approx(-122.42)

    @pytest.mark.asyncio
    async def test_unmapped_field_ignored(self, sink: CacheSink, cache: ResponseCache) -> None:
        frame = _frame(("UnknownFieldXYZ", 999, "whatever", "string"))
        await sink.on_frame(frame)
        sink.flush()

        result = cache.get(VIN)
        # Cache should either be None (no mapped data) or not contain unknown path
        if result is not None:
            assert "UnknownFieldXYZ" not in str(result.data)

    @pytest.mark.asyncio
    async def test_frame_count(self, sink: CacheSink) -> None:
        assert sink.frame_count == 0
        await sink.on_frame(_frame(("Soc", 3, 80, "int")))
        assert sink.frame_count == 1
        await sink.on_frame(_frame(("Soc", 3, 75, "int")))
        assert sink.frame_count == 2

    @pytest.mark.asyncio
    async def test_field_count(self, sink: CacheSink) -> None:
        frame = _frame(
            ("Soc", 3, 80, "int"),
            ("BatteryLevel", 8, 78, "int"),
        )
        await sink.on_frame(frame)
        assert sink.field_count == 2

    @pytest.mark.asyncio
    async def test_flush_interval_respected(
        self, cache: ResponseCache, mapper: TelemetryMapper
    ) -> None:
        # Large flush interval — first frame triggers immediate flush,
        # second frame should still be pending
        sink = CacheSink(cache, mapper, VIN, flush_interval=9999.0)
        await sink.on_frame(_frame(("Soc", 3, 80, "int")))
        # First frame flushes because last_flush starts at 0.0
        result = cache.get(VIN)
        assert result is not None

        # Second frame should buffer (interval not elapsed)
        await sink.on_frame(_frame(("BatteryLevel", 8, 78, "int")))
        assert sink.pending_count > 0

        # Manual flush should still work
        sink.flush()
        result = cache.get(VIN)
        assert result is not None
        assert result.data["charge_state"]["battery_level"] == 78

    @pytest.mark.asyncio
    async def test_empty_flush_is_noop(self, sink: CacheSink, cache: ResponseCache) -> None:
        sink.flush()  # no pending data
        assert cache.get(VIN) is None

    @pytest.mark.asyncio
    async def test_preserves_existing_cache_data(
        self, sink: CacheSink, cache: ResponseCache
    ) -> None:
        # Pre-populate cache with data not covered by telemetry
        cache.put(
            VIN,
            {
                "vin": VIN,
                "vehicle_config": {"car_type": "models"},
                "charge_state": {"charge_limit_soc": 90},
            },
        )

        # Telemetry updates a different charge_state field
        await sink.on_frame(_frame(("Soc", 3, 80, "int")))
        sink.flush()

        result = cache.get(VIN)
        assert result is not None
        # Telemetry data should be merged
        assert result.data["charge_state"]["usable_battery_level"] == 80
        # Existing data should be preserved
        assert result.data["charge_state"]["charge_limit_soc"] == 90
        assert result.data["vehicle_config"]["car_type"] == "models"

    @pytest.mark.asyncio
    async def test_gear_mapping(self, sink: CacheSink, cache: ResponseCache) -> None:
        frame = _frame(("Gear", 10, "Drive", "enum"))
        await sink.on_frame(frame)
        sink.flush()

        result = cache.get(VIN)
        assert result is not None
        assert result.data["drive_state"]["shift_state"] == "D"
