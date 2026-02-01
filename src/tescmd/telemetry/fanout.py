"""Fan-out dispatcher for telemetry frames.

Multiplexes a single ``on_frame`` callback to N sinks, each error-isolated.
One sink failing does not affect others.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from tescmd.telemetry.decoder import TelemetryFrame

logger = logging.getLogger(__name__)


class FrameFanout:
    """Fan-out dispatcher: delivers each telemetry frame to all registered sinks."""

    def __init__(self) -> None:
        self._sinks: list[Callable[[TelemetryFrame], Awaitable[None]]] = []

    def add_sink(self, callback: Callable[[TelemetryFrame], Awaitable[None]]) -> None:
        """Register a sink to receive telemetry frames."""
        self._sinks.append(callback)

    @property
    def sink_count(self) -> int:
        """Number of registered sinks."""
        return len(self._sinks)

    def has_sinks(self) -> bool:
        """Return ``True`` if at least one sink is registered."""
        return len(self._sinks) > 0

    async def on_frame(self, frame: TelemetryFrame) -> None:
        """Dispatch *frame* to all registered sinks.

        Each sink is called independently. If a sink raises, the exception
        is logged and the remaining sinks still receive the frame.
        """
        for sink in self._sinks:
            try:
                await sink(frame)
            except Exception:
                logger.warning("Sink %s failed for frame", sink, exc_info=True)
