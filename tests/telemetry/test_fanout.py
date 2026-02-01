"""Tests for the FrameFanout telemetry dispatcher."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from tescmd.telemetry.decoder import TelemetryDatum, TelemetryFrame
from tescmd.telemetry.fanout import FrameFanout


def _make_frame(
    vin: str = "5YJ3E1EA0KF000001", field: str = "Soc", value: int = 80
) -> TelemetryFrame:
    return TelemetryFrame(
        vin=vin,
        created_at=datetime.now(UTC),
        data=[TelemetryDatum(field_name=field, field_id=3, value=value, value_type="int")],
    )


class TestFrameFanout:
    def test_empty_fanout(self) -> None:
        fanout = FrameFanout()
        assert fanout.sink_count == 0
        assert not fanout.has_sinks()

    def test_add_sink(self) -> None:
        fanout = FrameFanout()
        fanout.add_sink(AsyncMock())
        assert fanout.sink_count == 1
        assert fanout.has_sinks()

    def test_add_multiple_sinks(self) -> None:
        fanout = FrameFanout()
        fanout.add_sink(AsyncMock())
        fanout.add_sink(AsyncMock())
        fanout.add_sink(AsyncMock())
        assert fanout.sink_count == 3

    @pytest.mark.asyncio
    async def test_dispatches_to_single_sink(self) -> None:
        fanout = FrameFanout()
        sink = AsyncMock()
        fanout.add_sink(sink)

        frame = _make_frame()
        await fanout.on_frame(frame)

        sink.assert_awaited_once_with(frame)

    @pytest.mark.asyncio
    async def test_dispatches_to_all_sinks(self) -> None:
        fanout = FrameFanout()
        sink_a = AsyncMock()
        sink_b = AsyncMock()
        sink_c = AsyncMock()
        fanout.add_sink(sink_a)
        fanout.add_sink(sink_b)
        fanout.add_sink(sink_c)

        frame = _make_frame()
        await fanout.on_frame(frame)

        sink_a.assert_awaited_once_with(frame)
        sink_b.assert_awaited_once_with(frame)
        sink_c.assert_awaited_once_with(frame)

    @pytest.mark.asyncio
    async def test_failing_sink_does_not_stop_others(self) -> None:
        fanout = FrameFanout()
        sink_a = AsyncMock()
        sink_b = AsyncMock(side_effect=RuntimeError("boom"))
        sink_c = AsyncMock()
        fanout.add_sink(sink_a)
        fanout.add_sink(sink_b)
        fanout.add_sink(sink_c)

        frame = _make_frame()
        await fanout.on_frame(frame)

        sink_a.assert_awaited_once_with(frame)
        sink_b.assert_awaited_once_with(frame)
        sink_c.assert_awaited_once_with(frame)

    @pytest.mark.asyncio
    async def test_multiple_frames(self) -> None:
        fanout = FrameFanout()
        sink = AsyncMock()
        fanout.add_sink(sink)

        frame1 = _make_frame(field="Soc", value=80)
        frame2 = _make_frame(field="BatteryLevel", value=78)
        await fanout.on_frame(frame1)
        await fanout.on_frame(frame2)

        assert sink.await_count == 2

    @pytest.mark.asyncio
    async def test_no_sinks_is_noop(self) -> None:
        fanout = FrameFanout()
        frame = _make_frame()
        await fanout.on_frame(frame)  # should not raise
