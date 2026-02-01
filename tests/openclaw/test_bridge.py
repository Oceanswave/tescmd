"""Tests for TelemetryBridge end-to-end frame → event flow."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from tescmd.openclaw.bridge import TelemetryBridge
from tescmd.openclaw.config import FieldFilter
from tescmd.openclaw.emitter import EventEmitter
from tescmd.openclaw.filters import DualGateFilter
from tescmd.openclaw.gateway import GatewayClient
from tescmd.telemetry.decoder import TelemetryDatum, TelemetryFrame


def _make_frame(
    vin: str = "VIN1",
    data: list[TelemetryDatum] | None = None,
) -> TelemetryFrame:
    return TelemetryFrame(
        vin=vin,
        created_at=datetime(2026, 1, 31, 12, 0, 0, tzinfo=UTC),
        data=data or [],
    )


@pytest.fixture()
def gateway() -> GatewayClient:
    gw = GatewayClient("ws://test:1234")
    gw._connected = True
    gw._ws = AsyncMock()
    gw._ws.send = AsyncMock()
    return gw


@pytest.fixture()
def bridge(gateway: GatewayClient) -> TelemetryBridge:
    filters = {
        "Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0),
        "Location": FieldFilter(granularity=0.0, throttle_seconds=0.0),
        "ChargeState": FieldFilter(granularity=0.0, throttle_seconds=0.0),
    }
    filt = DualGateFilter(filters)
    emitter = EventEmitter(client_id="test")
    return TelemetryBridge(gateway, filt, emitter)


class TestBridgeOnFrame:
    @pytest.mark.asyncio
    async def test_emit_mapped_datum(
        self, bridge: TelemetryBridge, gateway: GatewayClient
    ) -> None:
        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        assert bridge.event_count == 1
        assert bridge.drop_count == 0
        assert gateway._ws.send.call_count == 1

        sent = json.loads(gateway._ws.send.call_args[0][0])
        assert sent["method"] == "req:agent"
        assert sent["params"]["event_type"] == "battery"

    @pytest.mark.asyncio
    async def test_drop_unmapped_datum(self, bridge: TelemetryBridge) -> None:
        frame = _make_frame(data=[TelemetryDatum("UnknownField", 999, 42, "int")])
        await bridge.on_frame(frame)

        # UnknownField is not in the filter config, so it should be dropped
        assert bridge.event_count == 0
        assert bridge.drop_count == 1

    @pytest.mark.asyncio
    async def test_multiple_data_in_frame(
        self, bridge: TelemetryBridge, gateway: GatewayClient
    ) -> None:
        frame = _make_frame(
            data=[
                TelemetryDatum("Soc", 3, 72.0, "float"),
                TelemetryDatum("ChargeState", 2, "Charging", "enum"),
            ]
        )
        await bridge.on_frame(frame)

        assert bridge.event_count == 2
        assert gateway._ws.send.call_count == 2

    @pytest.mark.asyncio
    async def test_filter_drops_duplicate(self, bridge: TelemetryBridge) -> None:
        """Zero-granularity filter drops same value."""
        frame1 = _make_frame(data=[TelemetryDatum("ChargeState", 2, "Charging", "enum")])
        await bridge.on_frame(frame1)
        assert bridge.event_count == 1

        # Same value again — should be dropped by filter
        frame2 = _make_frame(data=[TelemetryDatum("ChargeState", 2, "Charging", "enum")])
        await bridge.on_frame(frame2)
        assert bridge.event_count == 1
        assert bridge.drop_count >= 1

    @pytest.mark.asyncio
    async def test_gateway_send_failure_does_not_crash(
        self, bridge: TelemetryBridge, gateway: GatewayClient
    ) -> None:
        gateway._ws.send = AsyncMock(side_effect=ConnectionError("broken"))
        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])

        # Should not raise
        await bridge.on_frame(frame)
        # Event was counted but send failed
        assert bridge.event_count == 1


class TestBridgeDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_prints_jsonl(
        self, gateway: GatewayClient, capsys: pytest.CaptureFixture[str]
    ) -> None:
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, dry_run=True)

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        captured = capsys.readouterr()
        line = json.loads(captured.out.strip())
        assert line["method"] == "req:agent"
        assert line["params"]["event_type"] == "battery"

        # Gateway should NOT have been called in dry-run
        assert gateway._ws.send.call_count == 0


class TestBridgeCounters:
    @pytest.mark.asyncio
    async def test_last_event_time_set(self, bridge: TelemetryBridge) -> None:
        assert bridge.last_event_time is None
        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)
        assert bridge.last_event_time is not None
