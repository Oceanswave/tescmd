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
from tescmd.triggers.manager import TriggerManager
from tescmd.triggers.models import TriggerCondition, TriggerDefinition, TriggerOperator


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
        # 1 connected lifecycle event + 1 data event = 2 sends
        assert gateway._ws.send.call_count == 2

        # Last send should be the data event
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
        # 1 connected lifecycle event + 2 data events = 3 sends
        assert gateway._ws.send.call_count == 3

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


class TestBridgeLifecycleEvents:
    """Tests for node.connected / node.disconnecting lifecycle events."""

    @pytest.mark.asyncio
    async def test_first_frame_sends_connected_event(self, gateway: GatewayClient) -> None:
        """First frame should trigger a node.connected event before data events."""
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test-client")

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        # First send should be the connected event, second the data event
        assert gateway._ws.send.call_count == 2
        first_msg = json.loads(gateway._ws.send.call_args_list[0][0][0])
        assert first_msg["method"] == "req:agent"
        assert first_msg["params"]["event_type"] == "node.connected"
        assert first_msg["params"]["vin"] == "VIN1"
        assert first_msg["params"]["source"] == "test-client"

    @pytest.mark.asyncio
    async def test_connected_event_sent_only_once(self, gateway: GatewayClient) -> None:
        """node.connected should only be sent on the first frame."""
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test-client")

        frame1 = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame1)
        # 1 connected + 1 data = 2
        assert gateway._ws.send.call_count == 2

        frame2 = _make_frame(data=[TelemetryDatum("Soc", 3, 80.0, "float")])
        await bridge.on_frame(frame2)
        # Only 1 more data event (no second connected) = 3
        assert gateway._ws.send.call_count == 3

    @pytest.mark.asyncio
    async def test_connected_event_not_sent_in_dry_run(self, gateway: GatewayClient) -> None:
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway, filt, emitter, dry_run=True, vin="VIN1", client_id="test"
        )

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        # Dry run doesn't send anything via gateway
        assert gateway._ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_connected_event_skipped_when_disconnected(self, gateway: GatewayClient) -> None:
        """No connected event if gateway is disconnected."""
        gateway._connected = False
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test")

        # Patch out reconnect to keep things simple
        bridge._reconnect_at = float("inf")

        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        # Nothing sent (gateway is disconnected)
        assert gateway._ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_send_disconnecting(self, gateway: GatewayClient) -> None:
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test-client")

        await bridge.send_disconnecting()

        assert gateway._ws.send.call_count == 1
        msg = json.loads(gateway._ws.send.call_args[0][0])
        assert msg["method"] == "req:agent"
        assert msg["params"]["event_type"] == "node.disconnecting"
        assert msg["params"]["vin"] == "VIN1"
        assert msg["params"]["source"] == "test-client"

    @pytest.mark.asyncio
    async def test_send_disconnecting_dry_run_is_noop(self, gateway: GatewayClient) -> None:
        filters = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway, filt, emitter, dry_run=True, vin="VIN1", client_id="test"
        )

        await bridge.send_disconnecting()
        assert gateway._ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_send_disconnecting_failure_does_not_raise(self, gateway: GatewayClient) -> None:
        """Disconnecting event failure should not crash shutdown."""
        gateway._ws.send = AsyncMock(side_effect=ConnectionError("broken"))
        filters = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test")

        # Should not raise
        await bridge.send_disconnecting()


class TestBuildOpenClawPipeline:
    """Tests for the build_openclaw_pipeline() factory function."""

    def test_factory_returns_all_components(self) -> None:
        from unittest.mock import MagicMock

        from tescmd.openclaw.bridge import OpenClawPipeline, build_openclaw_pipeline
        from tescmd.openclaw.config import BridgeConfig, NodeCapabilities

        app_ctx = MagicMock()
        config = BridgeConfig(
            gateway_url="ws://test:1234",
            gateway_token="tok",
            client_id="test-client",
            client_version="test/1.0",
            capabilities=NodeCapabilities(),
            telemetry={},
        )

        pipeline = build_openclaw_pipeline(config, "VIN1", app_ctx)

        assert isinstance(pipeline, OpenClawPipeline)
        assert isinstance(pipeline.gateway, GatewayClient)
        assert isinstance(pipeline.bridge, TelemetryBridge)
        assert isinstance(pipeline.telemetry_store, TelemetryStore)
        assert pipeline.dispatcher is not None

    def test_factory_passes_trigger_manager(self) -> None:
        from unittest.mock import MagicMock

        from tescmd.openclaw.bridge import build_openclaw_pipeline
        from tescmd.openclaw.config import BridgeConfig, NodeCapabilities

        app_ctx = MagicMock()
        config = BridgeConfig(
            gateway_url="ws://test:1234",
            gateway_token="tok",
            client_id="test-client",
            client_version="test/1.0",
            capabilities=NodeCapabilities(),
            telemetry={},
        )
        mgr = TriggerManager(vin="VIN1")

        pipeline = build_openclaw_pipeline(config, "VIN1", app_ctx, trigger_manager=mgr)

        # The bridge should have the trigger manager wired in
        assert pipeline.bridge._trigger_manager is mgr


class TestBridgeTriggerEvaluation:
    """Tests for trigger evaluation integrated with the bridge pipeline."""

    @pytest.mark.asyncio
    async def test_trigger_evaluated_on_frame(self, gateway: GatewayClient) -> None:
        """Trigger fires when threshold is crossed in a frame."""
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        mgr.create(TriggerDefinition(condition=cond))

        filters = {"BatteryLevel": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            telemetry_store=store,
            trigger_manager=mgr,
            vin="VIN1",
            client_id="test",
        )

        # First frame: value above threshold — no fire
        frame1 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 25.0, "float")])
        await bridge.on_frame(frame1)
        assert len(mgr.drain_pending()) == 0

        # Second frame: value below threshold — trigger fires
        frame2 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 15.0, "float")])
        await bridge.on_frame(frame2)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].field == "BatteryLevel"
        assert pending[0].value == 15.0
        assert pending[0].previous_value == 25.0

    @pytest.mark.asyncio
    async def test_previous_value_captured_before_store_update(
        self, gateway: GatewayClient
    ) -> None:
        """Previous value must be from BEFORE the store update."""
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.CHANGED)
        mgr.create(TriggerDefinition(condition=cond, cooldown_seconds=0))

        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            telemetry_store=store,
            trigger_manager=mgr,
        )

        # First frame: no previous value → CHANGED fires (None != 72.0)
        frame1 = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame1)
        n1 = mgr.drain_pending()
        assert len(n1) == 1
        assert n1[0].previous_value is None

        # After frame1, store should have Soc=72.0
        assert store.get("Soc").value == 72.0  # type: ignore[union-attr]

        # Second frame with same value — CHANGED does not fire
        frame2 = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame2)
        n2 = mgr.drain_pending()
        assert len(n2) == 0

        # Third frame with different value — fires with previous=72.0
        frame3 = _make_frame(data=[TelemetryDatum("Soc", 3, 80.0, "float")])
        await bridge.on_frame(frame3)
        n3 = mgr.drain_pending()
        assert len(n3) == 1
        assert n3[0].previous_value == 72.0
        assert n3[0].value == 80.0

    @pytest.mark.asyncio
    async def test_trigger_works_without_store(self, gateway: GatewayClient) -> None:
        """Triggers can fire even without a telemetry store (prev is always None)."""
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        mgr.create(TriggerDefinition(condition=cond))

        filters = {"BatteryLevel": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            trigger_manager=mgr,
        )

        # Value below threshold — fires (previous is None, which is fine for numeric ops)
        frame = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 15.0, "float")])
        await bridge.on_frame(frame)
        pending = mgr.drain_pending()
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_trigger_callback_invoked_from_bridge(self, gateway: GatewayClient) -> None:
        """Trigger fire callback is invoked when frame causes a trigger to fire."""
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="InsideTemp", operator=TriggerOperator.GT, value=100)
        mgr.create(TriggerDefinition(condition=cond))

        fired: list[object] = []
        mgr.add_on_fire(AsyncMock(side_effect=lambda n: fired.append(n)))

        filters = {"InsideTemp": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            telemetry_store=store,
            trigger_manager=mgr,
        )

        # First frame — establishes baseline
        frame1 = _make_frame(data=[TelemetryDatum("InsideTemp", 3, 95.0, "float")])
        await bridge.on_frame(frame1)
        assert len(fired) == 0

        # Second frame — crosses threshold
        frame2 = _make_frame(data=[TelemetryDatum("InsideTemp", 3, 105.0, "float")])
        await bridge.on_frame(frame2)
        assert len(fired) == 1

    @pytest.mark.asyncio
    async def test_end_to_end_threshold_crossing(self, gateway: GatewayClient) -> None:
        """Full pipeline: frame → store update → trigger fire → notification."""
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")

        # Create a battery low trigger
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LTE, value=10)
        mgr.create(TriggerDefinition(condition=cond, once=True))

        filters = {"BatteryLevel": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            telemetry_store=store,
            trigger_manager=mgr,
            vin="VIN1",
            client_id="test",
        )

        # Simulate battery draining: 50 → 20 → 10 → 5
        for level in [50.0, 20.0, 10.0, 5.0]:
            frame = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, level, "float")])
            await bridge.on_frame(frame)

        # One-shot trigger should have fired once (at level 10.0 crossing)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].value == 10.0
        assert pending[0].previous_value == 20.0

        # Trigger should be auto-deleted (one-shot)
        assert len(mgr.list_all()) == 0
