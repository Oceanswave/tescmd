"""Telemetry bridge orchestrator.

Wires the pipeline: TelemetryServer.on_frame → DualGateFilter → EventEmitter
→ GatewayClient. Passed as ``on_frame`` callback to ``TelemetryServer``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tescmd.openclaw.emitter import EventEmitter
    from tescmd.openclaw.filters import DualGateFilter
    from tescmd.openclaw.gateway import GatewayClient
    from tescmd.openclaw.telemetry_store import TelemetryStore
    from tescmd.telemetry.decoder import TelemetryFrame

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
    ) -> None:
        self._gateway = gateway
        self._filter = filt
        self._emitter = emitter
        self._dry_run = dry_run
        self._telemetry_store = telemetry_store
        self._event_count = 0
        self._drop_count = 0
        self._last_event_time: float | None = None
        self._reconnect_at: float = 0.0
        self._reconnect_backoff: float = _RECONNECT_BASE

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

    async def on_frame(self, frame: TelemetryFrame) -> None:
        """Process a decoded telemetry frame through the filter pipeline.

        For each datum in the frame, check the dual-gate filter. If it
        passes, transform to an OpenClaw event and send to the gateway.
        Failed sends are logged and discarded — never crash the server.
        If the gateway is disconnected, a reconnection attempt is made
        (with exponential backoff) before dropping events.
        """
        now = time.monotonic()

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

        # Update telemetry store with ALL datums (not just filtered ones)
        # so read handlers always see the latest values.
        if self._telemetry_store is not None:
            for datum in frame.data:
                self._telemetry_store.update(datum.field_name, datum.value, frame.created_at)
