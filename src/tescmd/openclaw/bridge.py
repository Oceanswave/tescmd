"""Telemetry bridge orchestrator.

Wires the pipeline: TelemetryServer.on_frame → DualGateFilter → EventEmitter
→ GatewayClient. Passed as ``on_frame`` callback to ``TelemetryServer``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext
    from tescmd.openclaw.config import BridgeConfig
    from tescmd.openclaw.emitter import EventEmitter
    from tescmd.openclaw.filters import DualGateFilter
    from tescmd.openclaw.gateway import GatewayClient
    from tescmd.openclaw.telemetry_store import TelemetryStore
    from tescmd.telemetry.decoder import TelemetryFrame
    from tescmd.triggers.manager import TriggerManager

logger = logging.getLogger(__name__)

_RECONNECT_BASE = 5.0
_RECONNECT_MAX = 120.0


class TelemetryBridge:
    """Orchestrates filter → emit → send for each telemetry frame.

    Usage::

        bridge = TelemetryBridge(config, gateway, filt, emitter)
        # Pass bridge.on_frame as the telemetry server callback
        server = TelemetryServer(port, decoder, bridge.on_frame, ...)
    """

    def __init__(
        self,
        gateway: GatewayClient,
        filt: DualGateFilter,
        emitter: EventEmitter,
        *,
        dry_run: bool = False,
        telemetry_store: TelemetryStore | None = None,
        trigger_manager: TriggerManager | None = None,
        vin: str = "",
        client_id: str = "node-host",
    ) -> None:
        self._gateway = gateway
        self._filter = filt
        self._emitter = emitter
        self._dry_run = dry_run
        self._telemetry_store = telemetry_store
        self._trigger_manager = trigger_manager
        self._vin = vin
        self._client_id = client_id
        self._event_count = 0
        self._drop_count = 0
        self._last_event_time: float | None = None
        self._first_frame_received = False
        self._reconnect_at: float = 0.0
        self._reconnect_backoff: float = _RECONNECT_BASE
        self._shutting_down = False

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def drop_count(self) -> int:
        return self._drop_count

    @property
    def last_event_time(self) -> float | None:
        return self._last_event_time

    async def _maybe_reconnect(self) -> None:
        """Attempt gateway reconnection with exponential backoff."""
        if self._shutting_down:
            return
        now = time.monotonic()
        if now < self._reconnect_at:
            return
        logger.info("Attempting OpenClaw gateway reconnection...")
        try:
            await self._gateway.connect()
            self._reconnect_backoff = _RECONNECT_BASE
            logger.info("Reconnected to OpenClaw gateway")
        except Exception:
            self._reconnect_at = now + self._reconnect_backoff
            logger.warning(
                "Reconnection failed — next attempt in %.0fs",
                self._reconnect_backoff,
            )
            self._reconnect_backoff = min(self._reconnect_backoff * 2, _RECONNECT_MAX)

    def _build_lifecycle_event(self, event_type: str) -> dict[str, Any]:
        """Build a ``req:agent`` lifecycle event (connecting/disconnecting)."""
        return {
            "method": "req:agent",
            "params": {
                "event_type": event_type,
                "source": self._client_id,
                "vin": self._vin,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {},
            },
        }

    def make_trigger_push_callback(self) -> Any:
        """Return an async callback that pushes trigger notifications to the gateway.

        Suitable for passing to ``TriggerManager.add_on_fire()``.  Returns
        ``None`` when in dry-run mode (caller should skip registration).
        """
        if self._dry_run:
            return None

        gateway = self._gateway
        client_id = self._client_id

        async def _push_trigger_notification(n: Any) -> None:
            if gateway.is_connected:
                try:
                    await gateway.send_event(
                        {
                            "method": "req:agent",
                            "params": {
                                "event_type": "trigger.fired",
                                "source": client_id,
                                "vin": n.vin,
                                "timestamp": n.fired_at.isoformat(),
                                "data": n.model_dump(mode="json"),
                            },
                        }
                    )
                except Exception:
                    logger.warning(
                        "Failed to push trigger notification (trigger=%s field=%s)",
                        n.trigger_id,
                        n.field,
                        exc_info=True,
                    )

        return _push_trigger_notification

    async def send_disconnecting(self) -> None:
        """Send a ``node.disconnecting`` lifecycle event to the gateway.

        Called during shutdown before the gateway connection is closed.
        Silently ignored if the gateway is not connected.
        """
        self._shutting_down = True
        if self._dry_run:
            return
        event = self._build_lifecycle_event("node.disconnecting")
        try:
            await self._gateway.send_event(event)
            logger.info("Sent node.disconnecting event")
        except Exception:
            logger.warning("Failed to send disconnecting event", exc_info=True)

    async def on_frame(self, frame: TelemetryFrame) -> None:
        """Process a decoded telemetry frame through the filter pipeline.

        For each datum in the frame, check the dual-gate filter. If it
        passes, transform to an OpenClaw event and send to the gateway.
        Failed sends are logged and discarded — never crash the server.
        If the gateway is disconnected, a reconnection attempt is made
        (with exponential backoff) before dropping events.
        """
        now = time.monotonic()

        # Send node.connected lifecycle event on the very first frame.
        if not self._first_frame_received:
            self._first_frame_received = True
            if not self._dry_run and self._gateway.is_connected:
                event = self._build_lifecycle_event("node.connected")
                try:
                    await self._gateway.send_event(event)
                    logger.info("Sent node.connected event")
                except Exception:
                    logger.warning("Failed to send connected event", exc_info=True)

        for datum in frame.data:
            if not self._filter.should_emit(datum.field_name, datum.value, now):
                self._drop_count += 1
                continue

            event = self._emitter.to_event(
                field_name=datum.field_name,
                value=datum.value,
                vin=frame.vin,
                timestamp=frame.created_at,
            )

            if event is None:
                self._drop_count += 1
                continue

            self._filter.record_emit(datum.field_name, datum.value, now)
            self._event_count += 1
            self._last_event_time = now

            if self._dry_run:
                import json

                print(json.dumps(event, default=str), flush=True)
                continue

            if not self._gateway.is_connected:
                await self._maybe_reconnect()
                if not self._gateway.is_connected:
                    self._drop_count += 1
                    continue

            try:
                await self._gateway.send_event(event)
                logger.info("Sent %s event for %s", datum.field_name, frame.vin)
            except Exception:
                logger.warning(
                    "Failed to send event for %s — discarding",
                    datum.field_name,
                    exc_info=True,
                )

        # Update telemetry store and evaluate triggers for ALL datums
        # (not just filtered ones) so read handlers always see the latest
        # values and triggers fire on every change.
        if self._telemetry_store is not None or self._trigger_manager is not None:
            for datum in frame.data:
                prev_snap = (
                    self._telemetry_store.get(datum.field_name)
                    if self._telemetry_store is not None
                    else None
                )
                prev_value = prev_snap.value if prev_snap is not None else None

                if self._telemetry_store is not None:
                    self._telemetry_store.update(datum.field_name, datum.value, frame.created_at)

                if self._trigger_manager is not None:
                    await self._trigger_manager.evaluate(
                        datum.field_name, datum.value, prev_value, frame.created_at
                    )


# -- Pipeline factory -------------------------------------------------------


@dataclass(frozen=True)
class OpenClawPipeline:
    """Holds all components of an assembled OpenClaw pipeline."""

    gateway: GatewayClient
    bridge: TelemetryBridge
    telemetry_store: TelemetryStore
    dispatcher: Any  # CommandDispatcher — avoids circular import


def build_openclaw_pipeline(
    config: BridgeConfig,
    vin: str,
    app_ctx: AppContext,
    *,
    trigger_manager: TriggerManager | None = None,
    dry_run: bool = False,
) -> OpenClawPipeline:
    """Construct the full OpenClaw pipeline from a :class:`BridgeConfig`.

    Returns an :class:`OpenClawPipeline` containing the gateway client,
    telemetry bridge, telemetry store, and command dispatcher — ready
    to be connected and wired into the telemetry fanout.

    After calling this, the caller should:

    1. ``await pipeline.gateway.connect_with_backoff(...)`` (unless dry-run)
    2. ``fanout.add_sink(pipeline.bridge.on_frame)``
    3. Optionally register the trigger push callback via
       ``pipeline.bridge.make_trigger_push_callback()``
    """
    from tescmd.openclaw.dispatcher import CommandDispatcher
    from tescmd.openclaw.emitter import EventEmitter
    from tescmd.openclaw.filters import DualGateFilter
    from tescmd.openclaw.gateway import GatewayClient
    from tescmd.openclaw.telemetry_store import TelemetryStore

    telemetry_store = TelemetryStore()
    dispatcher = CommandDispatcher(
        vin=vin,
        app_ctx=app_ctx,
        telemetry_store=telemetry_store,
        trigger_manager=trigger_manager,
    )
    filt = DualGateFilter(config.telemetry)
    emitter = EventEmitter(client_id=config.client_id)

    from tescmd import __version__

    gateway = GatewayClient(
        config.gateway_url,
        token=config.gateway_token,
        client_id=config.client_id,
        client_version=config.client_version,
        display_name=f"tescmd-{__version__}-{vin}",
        model_identifier=vin,
        capabilities=config.capabilities,
        on_request=dispatcher.dispatch,
    )
    bridge = TelemetryBridge(
        gateway,
        filt,
        emitter,
        dry_run=dry_run,
        telemetry_store=telemetry_store,
        vin=vin,
        client_id=config.client_id,
        trigger_manager=trigger_manager,
    )

    return OpenClawPipeline(
        gateway=gateway,
        bridge=bridge,
        telemetry_store=telemetry_store,
        dispatcher=dispatcher,
    )
