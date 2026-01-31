"""Async WebSocket server for receiving Fleet Telemetry pushes.

Listens on ``0.0.0.0`` so Tailscale Funnel (which terminates TLS)
can proxy to the local plain-WebSocket port.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import websockets.asyncio.server as ws_server

    from tescmd.telemetry.decoder import TelemetryDecoder, TelemetryFrame

logger = logging.getLogger(__name__)


class TelemetryServer:
    """Async WebSocket server that receives telemetry from vehicles."""

    def __init__(
        self,
        port: int,
        decoder: TelemetryDecoder,
        on_frame: Callable[[TelemetryFrame], Awaitable[None]],
    ) -> None:
        self._port = port
        self._decoder = decoder
        self._on_frame = on_frame
        self._server: ws_server.Server | None = None
        self._connection_count = 0
        self._frame_count = 0

    async def start(self) -> None:
        """Start the WebSocket server on ``0.0.0.0:{port}``."""
        try:
            import websockets.asyncio.server as ws_server_mod
        except ImportError as exc:
            from tescmd.api.errors import ConfigError

            raise ConfigError(
                "websockets is required for telemetry streaming. "
                "Install with: pip install tescmd[telemetry]"
            ) from exc

        self._server = await ws_server_mod.serve(
            self._handler,
            host="0.0.0.0",
            port=self._port,
        )
        logger.info("Telemetry WebSocket server listening on 0.0.0.0:%d", self._port)

    async def stop(self) -> None:
        """Gracefully shut down the server."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("Telemetry WebSocket server stopped")

    async def _handler(self, websocket: Any) -> None:
        """Handle a single vehicle WebSocket connection.

        Receives binary frames, decodes via :class:`TelemetryDecoder`,
        and dispatches to the ``on_frame`` callback. Malformed frames
        are logged and skipped — never crash the server.
        """
        self._connection_count += 1
        remote = getattr(websocket, "remote_address", ("unknown", 0))
        logger.info("Vehicle connected: %s (total: %d)", remote, self._connection_count)

        try:
            async for message in websocket:
                if isinstance(message, str):
                    # Tesla sends binary protobuf, but handle text gracefully
                    logger.debug("Received text frame (unexpected): %s", message[:200])
                    continue

                try:
                    frame = self._decoder.decode(message)
                    self._frame_count += 1
                    await self._on_frame(frame)
                except Exception:
                    logger.warning(
                        "Failed to decode telemetry frame (%d bytes)",
                        len(message),
                        exc_info=True,
                    )
        except Exception:
            logger.debug("Connection closed: %s", remote, exc_info=True)
        finally:
            self._connection_count -= 1
            logger.info("Vehicle disconnected: %s (remaining: %d)", remote, self._connection_count)

    @property
    def connection_count(self) -> int:
        """Number of currently active WebSocket connections."""
        return self._connection_count

    @property
    def frame_count(self) -> int:
        """Total number of telemetry frames decoded since server start."""
        return self._frame_count
