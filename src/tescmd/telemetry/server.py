"""Async WebSocket server for receiving Fleet Telemetry pushes.

Listens on all interfaces so Tailscale Funnel (which terminates TLS) can
proxy to the local plain-WebSocket port.

A lightweight TCP mux sits in front of the WebSocket server to handle
plain HTTP requests (HEAD, GET) that the ``websockets`` library rejects.
This is required because Tesla's Developer Portal sends HEAD requests to
validate Allowed Origin URLs, and browsers send GET requests for health
checks.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import websockets.asyncio.server as ws_server

    from tescmd.telemetry.decoder import TelemetryDecoder, TelemetryFrame

logger = logging.getLogger(__name__)

_HTTP_200 = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain\r\n"
    b"Content-Length: 24\r\n"
    b"\r\n"
    b"tescmd telemetry server\n"
)

_HTTP_200_HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 0\r\n\r\n"

_WELL_KNOWN_PATH = "/.well-known/appspecific/com.tesla.3p.public-key.pem"


class TelemetryServer:
    """Async WebSocket server that receives telemetry from vehicles.

    Internally runs two servers:

    * A **TCP mux** on ``0.0.0.0:{port}`` (the public-facing port that
      the tunnel proxy connects to).  It inspects the first HTTP request
      line and either responds directly (HEAD / plain GET) or forwards
      the connection to the internal WebSocket server.
    * A **websockets** server on ``127.0.0.1:{port+1}`` that handles
      actual WebSocket upgrade connections from vehicles.
    """

    def __init__(
        self,
        port: int,
        decoder: TelemetryDecoder,
        on_frame: Callable[[TelemetryFrame], Awaitable[None]],
        *,
        public_key_pem: str | None = None,
    ) -> None:
        self._port = port
        self._ws_port = port + 1
        self._decoder = decoder
        self._on_frame = on_frame
        self._public_key_pem = public_key_pem
        self._ws_server: ws_server.Server | None = None
        self._mux_server: asyncio.Server | None = None
        self._active_ws: set[Any] = set()
        self._connection_count = 0
        self._frame_count = 0

    async def start(self) -> None:
        """Start the mux + WebSocket servers."""
        import websockets.asyncio.server as ws_server_mod

        # Internal WS server — only reachable from localhost
        try:
            self._ws_server = await ws_server_mod.serve(
                self._ws_handler,
                host="127.0.0.1",
                port=self._ws_port,
            )
        except OSError as exc:
            raise OSError(
                f"Cannot bind internal WebSocket server to port {self._ws_port}: {exc}"
            ) from exc

        # Public-facing TCP mux — bind to all interfaces (IPv4 + IPv6).
        try:
            self._mux_server = await asyncio.start_server(
                self._mux_handler,
                host=None,
                port=self._port,
            )
        except OSError as exc:
            # Clean up the already-started WS server before re-raising
            if self._ws_server is not None:
                self._ws_server.close()
                await self._ws_server.wait_closed()
                self._ws_server = None
            raise OSError(f"Cannot bind mux server to port {self._port}: {exc}") from exc

        logger.info(
            "Telemetry server listening on 0.0.0.0:%d (ws internal :%d)",
            self._port,
            self._ws_port,
        )

    async def stop(self) -> None:
        """Gracefully shut down both servers and active connections."""
        # Close active WebSocket connections first
        for ws in list(self._active_ws):
            with contextlib.suppress(Exception):
                await ws.close()
        self._active_ws.clear()

        if self._mux_server is not None:
            self._mux_server.close()
            await self._mux_server.wait_closed()
            self._mux_server = None

        if self._ws_server is not None:
            self._ws_server.close()
            await self._ws_server.wait_closed()
            self._ws_server = None

        logger.info("Telemetry server stopped")

    # ------------------------------------------------------------------
    # TCP mux — inspects first request line, routes accordingly
    # ------------------------------------------------------------------

    async def _mux_handler(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Route an incoming TCP connection.

        * **HEAD** — immediate HTTP 200 (Tesla origin validation).
        * **GET without Upgrade** — immediate HTTP 200 (health check).
        * **GET with Upgrade: websocket** — forward to internal WS server.
        """
        try:
            first_line = await asyncio.wait_for(reader.readline(), timeout=10)
        except (TimeoutError, ConnectionError):
            writer.close()
            return

        if not first_line:
            writer.close()
            return

        parts = first_line.decode("latin-1").strip().split(" ", 2)
        method = parts[0].upper() if parts else ""
        path = parts[1] if len(parts) > 1 else "/"

        if method == "HEAD":
            if path == _WELL_KNOWN_PATH and self._public_key_pem is not None:
                pem_bytes = self._public_key_pem.encode()
                writer.write(
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/x-pem-file\r\n"
                    f"Content-Length: {len(pem_bytes)}\r\n"
                    f"\r\n".encode()
                )
            else:
                writer.write(_HTTP_200_HEAD)
            await writer.drain()
            writer.close()
            return

        if method != "GET":
            writer.write(_HTTP_200)
            await writer.drain()
            writer.close()
            return

        # Read remaining headers to check for WebSocket upgrade
        raw_headers: list[bytes] = []
        is_upgrade = False
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                raw_headers.append(line)
                if line in (b"\r\n", b"\n", b""):
                    break
                if line.lower().startswith(b"upgrade:") and b"websocket" in line.lower():
                    is_upgrade = True
        except (TimeoutError, ConnectionError):
            writer.close()
            return

        if not is_upgrade:
            if path == _WELL_KNOWN_PATH and self._public_key_pem is not None:
                pem_bytes = self._public_key_pem.encode()
                writer.write(
                    f"HTTP/1.1 200 OK\r\n"
                    f"Content-Type: application/x-pem-file\r\n"
                    f"Content-Length: {len(pem_bytes)}\r\n"
                    f"\r\n".encode()
                    + pem_bytes
                )
            else:
                writer.write(_HTTP_200)
            await writer.drain()
            writer.close()
            return

        # WebSocket upgrade — forward entire connection to internal WS server
        try:
            ws_reader, ws_writer = await asyncio.open_connection("127.0.0.1", self._ws_port)
        except ConnectionError:
            writer.close()
            return

        # Replay the already-read request line + headers
        ws_writer.write(first_line)
        for hdr in raw_headers:
            ws_writer.write(hdr)
        await ws_writer.drain()

        # Bidirectional pipe until either side closes
        await asyncio.gather(
            self._pipe(reader, ws_writer),
            self._pipe(ws_reader, writer),
        )

    @staticmethod
    async def _pipe(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Copy bytes from *reader* to *writer* until EOF."""
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    # ------------------------------------------------------------------
    # WebSocket handler
    # ------------------------------------------------------------------

    async def _ws_handler(self, websocket: Any) -> None:
        """Handle a single vehicle WebSocket connection.

        Receives binary frames, decodes via :class:`TelemetryDecoder`,
        and dispatches to the ``on_frame`` callback.  Malformed frames
        are logged and skipped — never crash the server.
        """
        self._connection_count += 1
        self._active_ws.add(websocket)
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
            self._active_ws.discard(websocket)
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
