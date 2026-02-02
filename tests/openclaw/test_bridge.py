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
from tescmd.openclaw.telemetry_store import TelemetryStore
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


class TestBridgeReconnection:
    @pytest.mark.asyncio
    async def test_reconnects_when_gateway_disconnected(self, gateway: GatewayClient) -> None:
        """Bridge reconnects and delivers the event after gateway drops."""
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter)

        # Simulate a disconnect.
        gateway._connected = False

        # Patch connect() to succeed and restore _connected.
        async def _mock_connect() -> None:
            gateway._connected = True

        gateway.connect = AsyncMock(side_effect=_mock_connect)  # type: ignore[method-assign]

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        gateway.connect.assert_awaited_once()
        assert gateway._ws.send.call_count == 1
        assert bridge.event_count == 1
        assert bridge.drop_count == 0

    @pytest.mark.asyncio
    async def test_drops_event_when_reconnect_fails(self, gateway: GatewayClient) -> None:
        """Events are dropped (not queued) when reconnection fails."""
        from tescmd.openclaw.gateway import GatewayConnectionError

        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter)

        gateway._connected = False
        gateway.connect = AsyncMock(  # type: ignore[method-assign]
            side_effect=GatewayConnectionError("refused"),
        )

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        # Event counted but dropped because gateway stayed disconnected.
        assert bridge.event_count == 1
        assert bridge.drop_count == 1
        assert gateway._ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_reconnect_backoff_skips_early_attempt(self, gateway: GatewayClient) -> None:
        """Second frame within backoff window doesn't attempt reconnect."""
        from tescmd.openclaw.gateway import GatewayConnectionError

        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter)

        gateway._connected = False
        gateway.connect = AsyncMock(  # type: ignore[method-assign]
            side_effect=GatewayConnectionError("refused"),
        )

        # First attempt — triggers reconnect, fails, sets backoff.
        frame1 = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame1)
        assert gateway.connect.await_count == 1

        # Second attempt immediately after — should skip reconnect (in backoff).
        frame2 = _make_frame(data=[TelemetryDatum("Soc", 3, 80.0, "float")])
        await bridge.on_frame(frame2)
        assert gateway.connect.await_count == 1  # Still 1, not 2


class TestBridgeCounters:
    @pytest.mark.asyncio
    async def test_last_event_time_set(self, bridge: TelemetryBridge) -> None:
        assert bridge.last_event_time is None
        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)
        assert bridge.last_event_time is not None


class TestBridgeTelemetryStore:
    @pytest.mark.asyncio
    async def test_store_updated_on_frame(self, gateway: GatewayClient) -> None:
        """All datums update the telemetry store, not just filtered ones."""
        store = TelemetryStore()
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, telemetry_store=store)

        frame = _make_frame(
            data=[
                TelemetryDatum("Soc", 3, 72.0, "float"),
                TelemetryDatum("UnknownField", 999, 42, "int"),  # not in filter
            ]
        )
        await bridge.on_frame(frame)

        # Both fields should be in the store (store gets ALL datums)
        assert store.get("Soc") is not None
        assert store.get("Soc").value == 72.0  # type: ignore[union-attr]
        assert store.get("UnknownField") is not None
        assert store.get("UnknownField").value == 42  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_store_not_required(self, gateway: GatewayClient) -> None:
        """Bridge works fine without a telemetry store."""
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter)  # no store

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)
        assert bridge.event_count == 1

    @pytest.mark.asyncio
    async def test_store_timestamp_matches_frame(self, gateway: GatewayClient) -> None:
        store = TelemetryStore()
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, telemetry_store=store)

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        snap = store.get("Soc")
        assert snap is not None
        assert snap.timestamp == frame.created_at
