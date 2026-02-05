"""Telemetry bridge orchestrator.

Wires the pipeline: TelemetryServer.on_frame → DualGateFilter → EventEmitter
→ GatewayClient. Passed as ``on_frame`` callback to ``TelemetryServer``.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext
    from tescmd.openclaw.config import BridgeConfig
    from tescmd.openclaw.dispatcher import CommandDispatcher
    from tescmd.openclaw.emitter import EventEmitter
    from tescmd.openclaw.filters import DualGateFilter
    from tescmd.openclaw.gateway import GatewayClient
    from tescmd.openclaw.telemetry_store import TelemetryStore
    from tescmd.telemetry.decoder import TelemetryFrame
    from tescmd.triggers.manager import TriggerManager

logger = logging.getLogger(__name__)

_RECONNECT_BASE = 5.0
_RECONNECT_MAX = 120.0
_MAX_PENDING_PUSH = 1000


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
        self._reconnect_at: float = 0.0
        self._reconnect_backoff: float = _RECONNECT_BASE
        self._shutting_down = False
        self._pending_push: deque[Any] = deque(maxlen=_MAX_PENDING_PUSH)

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
        except Exception:
            self._reconnect_at = now + self._reconnect_backoff
            logger.warning(
                "Reconnection failed — next attempt in %.0fs",
                self._reconnect_backoff,
                exc_info=True,
            )
            self._reconnect_backoff = min(self._reconnect_backoff * 2, _RECONNECT_MAX)
            return
        self._reconnect_backoff = _RECONNECT_BASE
        logger.info("Reconnected to OpenClaw gateway")
        try:
            await self.send_connected()
        except Exception:
            logger.warning("Failed to send connected event after reconnect", exc_info=True)
        # Flush any queued trigger notifications now that WS is available.
        if self._pending_push:
            try:
                await self.flush_pending_push()
            except Exception:
                logger.warning(
                    "Failed to flush %d pending push notification(s) after reconnect",
                    len(self._pending_push),
                    exc_info=True,
                )

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
        """Return an async callback that pushes trigger notifications.

        Delivery is via WebSocket (``gateway.send_event``).  On failure
        the notification is queued in ``_pending_push`` for later
        :meth:`flush_pending_push`.

        One-shot triggers (``n.once is True``) are deleted from the
        trigger manager only after confirmed delivery — guaranteeing the
        notification reaches the gateway before the trigger disappears.

        Returns ``None`` only when in dry-run mode (caller should skip
        registration).
        """
        if self._dry_run:
            return None

        gateway = self._gateway
        pending_push = self._pending_push
        trigger_manager = self._trigger_manager

        async def _push_trigger_notification(n: Any) -> None:
            if gateway.is_connected:
                try:
                    event = {
                        "method": "tescmd.trigger.fired",
                        "params": {
                            "trigger_id": n.trigger_id,
                            "field": n.field,
                            "operator": n.operator.value,
                            "value": n.value,
                            "vin": n.vin,
                            "fired_at": n.fired_at.isoformat(),
                        },
                    }
                except (AttributeError, TypeError, ValueError):
                    logger.error(
                        "Malformed trigger notification — discarding: %r",
                        n,
                        exc_info=True,
                    )
                    return
                await gateway.send_event(event)
                # send_event() never raises — check is_connected to detect failure.
                if gateway.is_connected:
                    logger.info(
                        "Pushed trigger notification: trigger=%s",
                        n.trigger_id,
                    )
                    if n.once and trigger_manager is not None:
                        trigger_manager.delete(n.trigger_id)
                        logger.info(
                            "Deleted one-shot trigger %s after confirmed delivery",
                            n.trigger_id,
                        )
                    return
                logger.warning(
                    "WS push failed for trigger=%s",
                    n.trigger_id,
                )

            if len(pending_push) == pending_push.maxlen:
                dropped = pending_push[0]
                logger.warning(
                    "Pending push queue full (%d) — dropping oldest: trigger=%s",
                    len(pending_push),
                    dropped.trigger_id,
                )
            pending_push.append(n)
            logger.warning(
                "Trigger notification queued: trigger=%s",
                n.trigger_id,
            )

        return _push_trigger_notification

    async def flush_pending_push(self) -> int:
        """Replay queued trigger notifications via WebSocket.

        One-shot triggers are deleted after each successful send,
        mirroring the behaviour of the push callback.

        Returns the number of notifications successfully flushed.
        """
        if not self._pending_push or self._dry_run:
            return 0
        if not self._gateway.is_connected:
            return 0

        total = len(self._pending_push)
        sent = 0

        while self._pending_push:
            n = self._pending_push[0]  # peek without removing
            try:
                event = {
                    "method": "tescmd.trigger.fired",
                    "params": {
                        "trigger_id": n.trigger_id,
                        "field": n.field,
                        "operator": n.operator.value,
                        "value": n.value,
                        "vin": n.vin,
                        "fired_at": n.fired_at.isoformat(),
                    },
                }
            except (AttributeError, TypeError, ValueError):
                logger.error(
                    "Malformed notification in push queue — discarding: %r",
                    n,
                    exc_info=True,
                )
                self._pending_push.popleft()
                continue
            await self._gateway.send_event(event)
            # send_event() never raises — check is_connected to detect failure.
            if not self._gateway.is_connected:
                logger.warning("Flush stopped at %d/%d", sent, total)
                break
            self._pending_push.popleft()
            sent += 1
            if n.once and self._trigger_manager is not None:
                self._trigger_manager.delete(n.trigger_id)
                logger.info(
                    "Deleted one-shot trigger %s after flush delivery",
                    n.trigger_id,
                )

        if sent:
            logger.info("Flushed %d/%d queued trigger notification(s)", sent, total)
        return sent

    async def send_connected(self) -> bool:
        """Send a ``node.connected`` lifecycle event to the gateway.

        Returns ``True`` if the event was sent (or skipped due to dry-run),
        ``False`` if the gateway was disconnected or the send failed.
        """
        if self._dry_run:
            return True
        if not self._gateway.is_connected:
            logger.warning("Cannot send node.connected — gateway not connected")
            return False
        event = self._build_lifecycle_event("node.connected")
        try:
            await self._gateway.send_event(event)
        except Exception:
            logger.warning("Failed to send connected event", exc_info=True)
            return False
        # send_event() swallows errors and marks disconnected, so check again.
        if not self._gateway.is_connected:
            logger.warning("Failed to send connected event — gateway disconnected during send")
            return False
        logger.info("Sent node.connected event")
        return True

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

    async def _send_datum(
        self,
        datum: Any,
        frame: TelemetryFrame,
        now: float,
    ) -> bool:
        """Emit a single datum as a gateway event.

        Returns ``True`` if the event was sent (or printed in dry-run mode).
        Handles reconnection and error logging internally.
        """
        event = self._emitter.to_event(
            field_name=datum.field_name,
            value=datum.value,
            vin=frame.vin,
            timestamp=frame.created_at,
        )

        if event is None:
            self._drop_count += 1
            return False

        self._filter.record_emit(datum.field_name, datum.value, now)
        self._event_count += 1
        self._last_event_time = now

        if self._dry_run:
            import json

            print(json.dumps(event, default=str), flush=True)
            return True

        if not self._gateway.is_connected:
            await self._maybe_reconnect()
            if not self._gateway.is_connected:
                self._drop_count += 1
                return False

        try:
            await self._gateway.send_event(event)
            logger.info("Sent %s event for %s", datum.field_name, frame.vin)
            return True
        except Exception:
            logger.warning(
                "Failed to send event for %s — discarding",
                datum.field_name,
                exc_info=True,
            )
            return False

    async def on_frame(self, frame: TelemetryFrame) -> None:
        """Process a decoded telemetry frame through the filter pipeline.

        For each datum in the frame, check the dual-gate filter. If it
        passes, transform to an OpenClaw event and send to the gateway.

        Trigger evaluation runs on **all** datums regardless of the filter.
        When a trigger fires on a datum that was blocked by the filter, the
        datum is force-emitted so the gateway always receives the value that
        caused the trigger to fire.

        Failed sends are logged and discarded — never crash the server.
        If the gateway is disconnected, a reconnection attempt is made
        (with exponential backoff) before dropping events.
        """
        now = time.monotonic()
        trigger_count = (
            len(self._trigger_manager.list_all()) if self._trigger_manager is not None else 0
        )
        logger.debug(
            "on_frame: vin=%s datums=%d connected=%s triggers=%d",
            frame.vin,
            len(frame.data),
            self._gateway.is_connected,
            trigger_count,
        )

        # --- Phase 1: filtered telemetry emission ---
        emitted = 0
        emitted_fields: set[str] = set()
        for datum in frame.data:
            if not self._filter.should_emit(datum.field_name, datum.value, now):
                self._drop_count += 1
                continue

            if await self._send_datum(datum, frame, now):
                emitted += 1
                emitted_fields.add(datum.field_name)

        if emitted > 0 or logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Frame summary: emitted=%d dropped=%d total_events=%d",
                emitted,
                self._drop_count,
                self._event_count,
            )

        # --- Phase 2: telemetry store + trigger evaluation ---
        # Runs on ALL datums (not just filtered ones) so read handlers
        # always see the latest values and triggers fire on every change.
        # When a trigger fires on a datum that wasn't emitted in phase 1,
        # force-emit it so the gateway receives the triggering value.
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
                    fired = await self._trigger_manager.evaluate(
                        datum.field_name, datum.value, prev_value, frame.created_at
                    )
                    # Force-emit the telemetry event when a trigger fires
                    # but the filter gate blocked it in phase 1.
                    if (
                        fired
                        and datum.field_name not in emitted_fields
                        and await self._send_datum(datum, frame, now)
                    ):
                        emitted_fields.add(datum.field_name)
                        logger.info(
                            "Force-emitted %s for %s (trigger fired)",
                            datum.field_name,
                            frame.vin,
                        )


# -- Pipeline factory -------------------------------------------------------


@dataclass(frozen=True)
class OpenClawPipeline:
    """Holds all components of an assembled OpenClaw pipeline."""

    gateway: GatewayClient
    bridge: TelemetryBridge
    telemetry_store: TelemetryStore
    dispatcher: CommandDispatcher


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

    # bridge is assigned below, but the closure captures it by reference —
    # on_reconnect is only called during live reconnection, long after this
    # function returns, so bridge is always initialised by then.
    bridge: TelemetryBridge | None = None

    async def _on_reconnect() -> None:
        if bridge is not None:
            await bridge.send_connected()
        else:
            logger.error("on_reconnect fired but bridge is None — this should never happen")

    gateway = GatewayClient(
        config.gateway_url,
        token=config.gateway_token,
        client_id=config.client_id,
        client_version=config.client_version,
        display_name=f"tescmd-{__version__}-{vin}",
        model_identifier=vin,
        capabilities=config.capabilities,
        on_request=dispatcher.dispatch,
        on_reconnect=_on_reconnect,
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
