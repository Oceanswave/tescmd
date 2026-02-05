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
from tescmd.triggers.models import (
    TriggerCondition,
    TriggerDefinition,
    TriggerNotification,
    TriggerOperator,
)


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
    async def test_unmapped_datum_emits_generic_event(self, bridge: TelemetryBridge) -> None:
        frame = _make_frame(data=[TelemetryDatum("UnknownField", 999, 42, "int")])
        await bridge.on_frame(frame)

        # UnknownField has no explicit filter config but the default
        # fallback allows it through, producing a generic event.
        assert bridge.event_count == 1
        assert bridge.drop_count == 0

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
        # 1 connected lifecycle event (from reconnect) + 1 data event = 2 sends
        assert gateway._ws.send.call_count == 2
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
    async def test_send_connected(self, gateway: GatewayClient) -> None:
        """Calling send_connected() sends a node.connected event to the gateway."""
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test-client")

        assert await bridge.send_connected() is True

        assert gateway._ws.send.call_count == 1
        msg = json.loads(gateway._ws.send.call_args[0][0])
        assert msg["method"] == "req:agent"
        assert msg["params"]["event_type"] == "node.connected"
        assert msg["params"]["vin"] == "VIN1"
        assert msg["params"]["source"] == "test-client"

    @pytest.mark.asyncio
    async def test_on_frame_does_not_send_connected(self, gateway: GatewayClient) -> None:
        """on_frame() should only send data events, never connected events."""
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test-client")

        frame1 = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame1)
        # Only the data event, no connected event
        assert gateway._ws.send.call_count == 1
        msg = json.loads(gateway._ws.send.call_args[0][0])
        assert msg["params"]["event_type"] == "battery"

        frame2 = _make_frame(data=[TelemetryDatum("Soc", 3, 80.0, "float")])
        await bridge.on_frame(frame2)
        # One more data event
        assert gateway._ws.send.call_count == 2

    @pytest.mark.asyncio
    async def test_send_connected_not_sent_in_dry_run(self, gateway: GatewayClient) -> None:
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway, filt, emitter, dry_run=True, vin="VIN1", client_id="test"
        )

        # Dry-run is considered success (nothing to send)
        assert await bridge.send_connected() is True

        # Gateway should NOT have been called in dry-run
        assert gateway._ws.send.call_count == 0

    @pytest.mark.asyncio
    async def test_reconnect_sends_connected(self, gateway: GatewayClient) -> None:
        """Successful reconnect in _maybe_reconnect() sends node.connected."""
        filters = {"Soc": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test-client")

        # Simulate disconnected state so _maybe_reconnect is invoked.
        gateway._connected = False

        async def _mock_connect() -> None:
            gateway._connected = True

        gateway.connect = AsyncMock(side_effect=_mock_connect)  # type: ignore[method-assign]

        # Trigger reconnect via on_frame with a mapped datum.
        frame = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame)

        gateway.connect.assert_awaited_once()
        # 1 connected lifecycle event (from reconnect) + 1 data event = 2
        assert gateway._ws.send.call_count == 2
        first_msg = json.loads(gateway._ws.send.call_args_list[0][0][0])
        assert first_msg["params"]["event_type"] == "node.connected"

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
    async def test_send_connected_failure_does_not_raise(self, gateway: GatewayClient) -> None:
        """Connected event failure should not crash, returns False."""
        gateway._ws.send = AsyncMock(side_effect=ConnectionError("broken"))
        filters = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test")

        # Should not raise, but should report failure
        assert await bridge.send_connected() is False

    @pytest.mark.asyncio
    async def test_send_connected_skipped_when_disconnected(self, gateway: GatewayClient) -> None:
        """send_connected() returns False when gateway is not connected."""
        gateway._connected = False
        filters = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(gateway, filt, emitter, vin="VIN1", client_id="test")

        assert await bridge.send_connected() is False

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

        fired: list[TriggerNotification] = []
        mgr.add_on_fire(AsyncMock(side_effect=lambda n: fired.append(n)))

        # First frame: value above threshold — no fire
        frame1 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 25.0, "float")])
        await bridge.on_frame(frame1)
        assert len(fired) == 0

        # Second frame: value below threshold — trigger fires
        frame2 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 15.0, "float")])
        await bridge.on_frame(frame2)
        assert len(fired) == 1
        assert fired[0].field == "BatteryLevel"
        assert fired[0].value == 15.0
        assert fired[0].previous_value == 25.0

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

        fired: list[TriggerNotification] = []
        mgr.add_on_fire(AsyncMock(side_effect=lambda n: fired.append(n)))

        # First frame: no previous value → CHANGED fires (None != 72.0)
        frame1 = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame1)
        assert len(fired) == 1
        assert fired[0].previous_value is None

        # After frame1, store should have Soc=72.0
        assert store.get("Soc").value == 72.0  # type: ignore[union-attr]

        # Second frame with same value — CHANGED does not fire
        frame2 = _make_frame(data=[TelemetryDatum("Soc", 3, 72.0, "float")])
        await bridge.on_frame(frame2)
        assert len(fired) == 1  # still 1

        # Third frame with different value — fires with previous=72.0
        frame3 = _make_frame(data=[TelemetryDatum("Soc", 3, 80.0, "float")])
        await bridge.on_frame(frame3)
        assert len(fired) == 2
        assert fired[1].previous_value == 72.0
        assert fired[1].value == 80.0

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

        fired: list[TriggerNotification] = []
        mgr.add_on_fire(AsyncMock(side_effect=lambda n: fired.append(n)))

        # Value below threshold — fires (previous is None, which is fine for numeric ops)
        frame = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 15.0, "float")])
        await bridge.on_frame(frame)
        assert len(fired) == 1

    @pytest.mark.asyncio
    async def test_trigger_callback_invoked_from_bridge(self, gateway: GatewayClient) -> None:
        """Trigger fire callback is invoked when frame causes a trigger to fire."""
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        # Threshold 35°C (~95°F) — realistic cabin temperature in Celsius
        cond = TriggerCondition(field="InsideTemp", operator=TriggerOperator.GT, value=35)
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

        # First frame — 30°C (86°F), below threshold
        frame1 = _make_frame(data=[TelemetryDatum("InsideTemp", 3, 30.0, "float")])
        await bridge.on_frame(frame1)
        assert len(fired) == 0

        # Second frame — 40°C (104°F), crosses threshold
        frame2 = _make_frame(data=[TelemetryDatum("InsideTemp", 3, 40.0, "float")])
        await bridge.on_frame(frame2)
        assert len(fired) == 1

    @pytest.mark.asyncio
    async def test_end_to_end_threshold_crossing(self, gateway: GatewayClient) -> None:
        """Full pipeline: frame → store update → trigger fire → notification.

        One-shot trigger fires once but stays registered (pending delivery).
        It only fires once despite subsequent matching frames.
        """
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")

        # Create a battery low trigger
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LTE, value=10)
        mgr.create(TriggerDefinition(condition=cond, once=True))

        filters = {"BatteryLevel": FieldFilter(granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        fired: list[TriggerNotification] = []
        mgr.add_on_fire(AsyncMock(side_effect=lambda n: fired.append(n)))

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
        assert len(fired) == 1
        assert fired[0].value == 10.0
        assert fired[0].previous_value == 20.0
        assert fired[0].once is True

        # Trigger stays registered (pending delivery confirmation)
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_trigger_force_emits_filtered_datum(self, gateway: GatewayClient) -> None:
        """When a trigger fires on a datum blocked by the filter, force-emit it."""
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        mgr.create(TriggerDefinition(condition=cond))

        # High granularity so small changes are blocked by the delta gate
        filters = {"BatteryLevel": FieldFilter(granularity=50.0, throttle_seconds=0.0)}
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

        # First frame: above threshold — emitted (first value always passes)
        frame1 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 25.0, "float")])
        await bridge.on_frame(frame1)
        assert gateway._ws.send.call_count == 1  # filter passed (first value)

        # Second frame: below threshold, small delta (10 < 50 granularity)
        # Filter would block it, but trigger fires → force-emit
        frame2 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 15.0, "float")])
        await bridge.on_frame(frame2)
        # 1 (filter-passed) + 1 (force-emitted due to trigger) = 2
        assert gateway._ws.send.call_count == 2

    @pytest.mark.asyncio
    async def test_trigger_no_double_emit(self, gateway: GatewayClient) -> None:
        """When a trigger fires on a datum already emitted by the filter, don't double-send."""
        store = TelemetryStore()
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        mgr.create(TriggerDefinition(condition=cond))

        # Granularity 0 so everything passes the delta gate
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

        # First frame: above threshold
        frame1 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 25.0, "float")])
        await bridge.on_frame(frame1)
        assert gateway._ws.send.call_count == 1

        # Second frame: below threshold — filter passes AND trigger fires
        # Should only emit once (no double-send)
        frame2 = _make_frame(data=[TelemetryDatum("BatteryLevel", 3, 15.0, "float")])
        await bridge.on_frame(frame2)
        assert gateway._ws.send.call_count == 2  # exactly 1 more, not 2


class TestTriggerPushCallback:
    """Tests for the WS-based trigger push callback and flush."""

    def _make_notification(
        self, trigger_id: str = "t1", field: str = "BatteryLevel", value: float = 15.0
    ) -> TriggerNotification:
        return TriggerNotification(
            trigger_id=trigger_id,
            field=field,
            operator=TriggerOperator.LT,
            threshold=20,
            value=value,
            previous_value=25.0,
            fired_at=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
            vin="VIN1",
        )

    @pytest.mark.asyncio
    async def test_push_callback_sends_via_ws(self, gateway: GatewayClient) -> None:
        """Push callback sends via WS when gateway is connected."""
        mgr = TriggerManager(vin="VIN1")
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
            trigger_manager=mgr,
        )

        cb = bridge.make_trigger_push_callback()
        assert cb is not None

        gateway._ws = AsyncMock()
        gateway._ws.send = AsyncMock()
        await cb(self._make_notification())

        gateway._ws.send.assert_awaited_once()
        assert len(bridge._pending_push) == 0

    @pytest.mark.asyncio
    async def test_push_callback_queues_when_disconnected(
        self,
        gateway: GatewayClient,
    ) -> None:
        """Push callback queues when gateway is disconnected."""
        gateway._connected = False
        gateway._ws = None
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
        )

        cb = bridge.make_trigger_push_callback()
        assert cb is not None

        await cb(self._make_notification())
        assert len(bridge._pending_push) == 1

    @pytest.mark.asyncio
    async def test_push_callback_queues_on_ws_failure(
        self,
        gateway: GatewayClient,
    ) -> None:
        """Push callback queues when gateway is connected but send_event raises."""
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
        )

        cb = bridge.make_trigger_push_callback()
        assert cb is not None

        gateway._ws = AsyncMock()
        gateway._ws.send = AsyncMock(side_effect=ConnectionError("broken"))
        await cb(self._make_notification())

        assert len(bridge._pending_push) == 1

    @pytest.mark.asyncio
    async def test_flush_sends_queued_via_ws(
        self,
        gateway: GatewayClient,
    ) -> None:
        """flush_pending_push sends via WS when gateway is connected."""
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
        )

        bridge._pending_push.append(self._make_notification("t1"))
        bridge._pending_push.append(self._make_notification("t2"))

        gateway._ws = AsyncMock()
        gateway._ws.send = AsyncMock()

        sent = await bridge.flush_pending_push()
        assert sent == 2
        assert len(bridge._pending_push) == 0
        assert gateway._ws.send.await_count == 2

    @pytest.mark.asyncio
    async def test_flush_stops_on_ws_failure(
        self,
        gateway: GatewayClient,
    ) -> None:
        """flush_pending_push stops when WS send fails mid-flush."""
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
        )

        bridge._pending_push.append(self._make_notification("t1"))
        bridge._pending_push.append(self._make_notification("t2"))

        gateway._ws = AsyncMock()
        call_count = 0

        async def _send_side_effect(data: str) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise ConnectionError("broken")

        gateway._ws.send = AsyncMock(side_effect=_send_side_effect)

        sent = await bridge.flush_pending_push()
        assert sent == 1
        assert len(bridge._pending_push) == 1

    @pytest.mark.asyncio
    async def test_flush_noop_when_empty(self, gateway: GatewayClient) -> None:
        """flush_pending_push returns 0 when queue is empty."""
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
        )

        sent = await bridge.flush_pending_push()
        assert sent == 0

    @pytest.mark.asyncio
    async def test_flush_noop_when_disconnected(self, gateway: GatewayClient) -> None:
        """flush_pending_push returns 0 when gateway is disconnected."""
        gateway._connected = False
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
        )

        bridge._pending_push.append(self._make_notification("t1"))

        sent = await bridge.flush_pending_push()
        assert sent == 0
        assert len(bridge._pending_push) == 1

    @pytest.mark.asyncio
    async def test_push_callback_deletes_once_trigger_on_delivery(
        self,
        gateway: GatewayClient,
    ) -> None:
        """Push callback deletes one-shot trigger after confirmed WS delivery."""
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        t = mgr.create(TriggerDefinition(condition=cond, once=True))

        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
            trigger_manager=mgr,
        )

        cb = bridge.make_trigger_push_callback()
        assert cb is not None

        gateway._ws = AsyncMock()
        gateway._ws.send = AsyncMock()

        n = self._make_notification(trigger_id=t.id)
        # Simulate once=True on notification (as set by evaluate)
        n = TriggerNotification(
            trigger_id=t.id,
            field="BatteryLevel",
            operator=TriggerOperator.LT,
            threshold=20,
            value=15.0,
            previous_value=25.0,
            fired_at=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
            vin="VIN1",
            once=True,
        )
        await cb(n)

        # Trigger should be deleted after confirmed delivery
        assert len(mgr.list_all()) == 0
        assert len(bridge._pending_push) == 0

    @pytest.mark.asyncio
    async def test_push_callback_keeps_once_trigger_on_failure(
        self,
        gateway: GatewayClient,
    ) -> None:
        """Push callback queues notification and keeps trigger when WS fails."""
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        t = mgr.create(TriggerDefinition(condition=cond, once=True))

        gateway._connected = False
        gateway._ws = None
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
            trigger_manager=mgr,
        )

        cb = bridge.make_trigger_push_callback()
        assert cb is not None

        n = TriggerNotification(
            trigger_id=t.id,
            field="BatteryLevel",
            operator=TriggerOperator.LT,
            threshold=20,
            value=15.0,
            previous_value=25.0,
            fired_at=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
            vin="VIN1",
            once=True,
        )
        await cb(n)

        # Trigger stays — delivery not confirmed
        assert len(mgr.list_all()) == 1
        assert len(bridge._pending_push) == 1

    @pytest.mark.asyncio
    async def test_flush_deletes_once_trigger_on_delivery(
        self,
        gateway: GatewayClient,
    ) -> None:
        """flush_pending_push deletes one-shot trigger after confirmed delivery."""
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        t = mgr.create(TriggerDefinition(condition=cond, once=True))

        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
            trigger_manager=mgr,
        )

        n = TriggerNotification(
            trigger_id=t.id,
            field="BatteryLevel",
            operator=TriggerOperator.LT,
            threshold=20,
            value=15.0,
            previous_value=25.0,
            fired_at=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
            vin="VIN1",
            once=True,
        )
        bridge._pending_push.append(n)

        gateway._ws = AsyncMock()
        gateway._ws.send = AsyncMock()

        sent = await bridge.flush_pending_push()
        assert sent == 1
        assert len(bridge._pending_push) == 0
        # Trigger deleted after flush delivery
        assert len(mgr.list_all()) == 0

    @pytest.mark.asyncio
    async def test_flush_keeps_persistent_trigger(
        self,
        gateway: GatewayClient,
    ) -> None:
        """flush_pending_push does NOT delete persistent triggers."""
        mgr = TriggerManager(vin="VIN1")
        cond = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        t = mgr.create(TriggerDefinition(condition=cond, once=False))

        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            vin="VIN1",
            client_id="test-client",
            trigger_manager=mgr,
        )

        n = TriggerNotification(
            trigger_id=t.id,
            field="BatteryLevel",
            operator=TriggerOperator.LT,
            threshold=20,
            value=15.0,
            previous_value=25.0,
            fired_at=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
            vin="VIN1",
            once=False,
        )
        bridge._pending_push.append(n)

        gateway._ws = AsyncMock()
        gateway._ws.send = AsyncMock()

        sent = await bridge.flush_pending_push()
        assert sent == 1
        # Persistent trigger stays
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_push_callback_none_in_dry_run(
        self,
        gateway: GatewayClient,
    ) -> None:
        """make_trigger_push_callback returns None in dry-run mode."""
        filters: dict[str, FieldFilter] = {}
        filt = DualGateFilter(filters)
        emitter = EventEmitter(client_id="test")
        bridge = TelemetryBridge(
            gateway,
            filt,
            emitter,
            dry_run=True,
            vin="VIN1",
            client_id="test",
        )

        cb = bridge.make_trigger_push_callback()
        assert cb is None
