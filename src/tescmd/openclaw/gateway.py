"""WebSocket client for the OpenClaw Gateway.

Implements the OpenClaw operator protocol:

1. Receive ``connect.challenge`` event with nonce
2. Send ``connect`` request with operator role, scopes, auth token
3. Receive ``hello-ok`` response
4. Emit events via ``req:agent`` method

Includes exponential backoff reconnection (1s base → 60s max) with jitter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

logger = logging.getLogger(__name__)

_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 60.0
_BACKOFF_FACTOR = 2.0


class GatewayConnectionError(Exception):
    """Failed to connect or authenticate with the OpenClaw Gateway."""


class GatewayClient:
    """Manages WebSocket connection to an OpenClaw Gateway (operator role)."""

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        client_id: str = "tescmd-bridge",
        client_version: str = "0.1.0",
    ) -> None:
        self._url = url
        self._token = token
        self._client_id = client_id
        self._client_version = client_version
        self._ws: Any = None
        self._connected = False
        self._send_count = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def send_count(self) -> int:
        return self._send_count

    async def connect(self) -> None:
        """Connect to the gateway and complete the handshake.

        Raises :class:`GatewayConnectionError` on failure.
        """
        import websockets.asyncio.client as ws_client

        try:
            self._ws = await ws_client.connect(self._url)
        except Exception as exc:
            raise GatewayConnectionError(
                f"Failed to connect to gateway at {self._url}: {exc}"
            ) from exc

        await self._handshake()
        self._connected = True
        logger.info("Connected to OpenClaw Gateway at %s", self._url)

    async def _handshake(self) -> None:
        """Complete the OpenClaw connect challenge → hello-ok handshake."""
        assert self._ws is not None

        # Receive challenge
        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        msg = json.loads(raw)

        if msg.get("event") != "connect.challenge":
            raise GatewayConnectionError(
                f"Expected connect.challenge, got: {msg.get('event', 'unknown')}"
            )

        nonce = msg.get("data", {}).get("nonce", "")

        # Send connect request
        params: dict[str, Any] = {
            "role": "operator",
            "scopes": ["operator.send"],
            "client_id": self._client_id,
            "client_version": self._client_version,
            "nonce": nonce,
        }
        if self._token:
            params["token"] = self._token
        connect_msg: dict[str, Any] = {"method": "connect", "params": params}

        await self._ws.send(json.dumps(connect_msg))

        # Receive hello-ok
        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        msg = json.loads(raw)

        if msg.get("event") != "hello-ok":
            error = msg.get("error", msg.get("event", "unknown"))
            raise GatewayConnectionError(f"Handshake failed: {error}")

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send an event to the gateway.

        Silently drops the event if not connected. Never raises on send
        failure — logs and marks as disconnected instead.
        """
        if not self._connected or self._ws is None:
            return

        try:
            await self._ws.send(json.dumps(event))
            self._send_count += 1
        except Exception:
            logger.warning("Send failed — marking gateway as disconnected")
            self._connected = False

    async def close(self) -> None:
        """Close the gateway connection gracefully."""
        import contextlib

        self._connected = False
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

    async def connect_with_backoff(self, *, max_attempts: int = 0) -> None:
        """Connect with exponential backoff retry.

        Parameters
        ----------
        max_attempts:
            Maximum connection attempts. ``0`` means infinite.
        """
        attempt = 0
        backoff = _BACKOFF_BASE

        while max_attempts == 0 or attempt < max_attempts:
            attempt += 1
            try:
                await self.connect()
                return
            except GatewayConnectionError as exc:
                if max_attempts > 0 and attempt >= max_attempts:
                    raise
                jitter = random.uniform(0, backoff * 0.1)
                wait = min(backoff + jitter, _BACKOFF_MAX)
                logger.info(
                    "Connection attempt %d failed: %s — retrying in %.1fs",
                    attempt,
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)
                backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_MAX)
