"""WebSocket client for the OpenClaw Gateway.

Implements the OpenClaw node protocol (bidirectional):

1. Receive ``connect.challenge`` event (type=event) with nonce + ts
2. Sign a pipe-delimited auth payload with the device Ed25519 key
3. Send ``connect`` request (type=req) with role, scopes, capabilities,
   auth, device
4. Receive ``hello-ok`` event
5. OUTBOUND: Emit events via ``req:agent`` method (type=req)
6. INBOUND:  Receive ``node.invoke.request`` events → dispatch →
   send ``node.invoke.result`` requests

Frame types:
  - Request:  ``{type: "req",   id, method, params}``
  - Response: ``{type: "res",   id, ok, payload|error}``
  - Event:    ``{type: "event", event, payload, seq?, stateVersion?}``

Includes exponential backoff reconnection (1s base → 60s max) with jitter.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import platform
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from websockets.asyncio.client import ClientConnection

    from tescmd.openclaw.config import NodeCapabilities

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

logger = logging.getLogger(__name__)

_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 60.0
_BACKOFF_FACTOR = 2.0

_PROTOCOL_VERSION = 3

_DEVICE_KEY_FILE = "device-key.pem"


def _device_key_dir() -> Path:
    """Return the directory for the OpenClaw device key, respecting TESLA_CONFIG_DIR."""
    import os

    config_dir = os.environ.get("TESLA_CONFIG_DIR", "~/.config/tescmd")
    return Path(config_dir).expanduser() / "openclaw"


# -- Helpers ----------------------------------------------------------------


async def _retry_with_backoff(
    operation: Callable[[], Awaitable[None]],
    *,
    label: str = "operation",
    max_attempts: int = 0,
) -> None:
    """Retry *operation* with exponential backoff and jitter.

    Parameters
    ----------
    operation:
        Async callable to attempt.
    label:
        Human-readable label for log messages.
    max_attempts:
        Maximum number of attempts. ``0`` means unlimited.

    Raises the last exception if *max_attempts* is reached.
    """
    attempt = 0
    backoff = _BACKOFF_BASE
    while max_attempts == 0 or attempt < max_attempts:
        attempt += 1
        try:
            await operation()
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if max_attempts > 0 and attempt >= max_attempts:
                raise
            jitter = random.uniform(0, backoff * 0.1)
            wait = min(backoff + jitter, _BACKOFF_MAX)
            logger.info(
                "%s attempt %d failed: %s — retrying in %.1fs",
                label,
                attempt,
                exc,
                wait,
            )
            await asyncio.sleep(wait)
            backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_MAX)


def _b64url(data: bytes) -> str:
    """Base64URL-encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# -- Device identity helpers ------------------------------------------------


def _ensure_device_key() -> Ed25519PrivateKey:
    """Load or generate the device Ed25519 keypair for gateway auth."""
    key_dir = _device_key_dir()
    key_dir.mkdir(parents=True, exist_ok=True)
    key_path = key_dir / _DEVICE_KEY_FILE

    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if isinstance(key, Ed25519PrivateKey):
            return key

    # Generate a new Ed25519 device key.
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem)
    key_path.chmod(0o600)
    logger.info("Generated OpenClaw device key: %s", key_path)
    return private_key


def _public_key_raw(key: Ed25519PrivateKey) -> bytes:
    """Return the raw 32-byte Ed25519 public key."""
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _public_key_raw_b64url(key: Ed25519PrivateKey) -> str:
    """Return the raw 32-byte Ed25519 public key as base64url."""
    return _b64url(_public_key_raw(key))


def _device_id(key: Ed25519PrivateKey) -> str:
    """Derive a stable device ID from the public key (full SHA-256 hex)."""
    return hashlib.sha256(_public_key_raw(key)).hexdigest()


def _build_auth_payload(
    *,
    device_id: str,
    client_id: str,
    client_mode: str,
    role: str,
    scopes: list[str],
    signed_at_ms: int,
    token: str | None,
    nonce: str | None,
) -> str:
    """Build the pipe-delimited payload string that gets signed.

    v2 (with nonce): ``v2|deviceId|clientId|mode|role|scopes|ts|token|nonce``
    v1 (no nonce):   ``v1|deviceId|clientId|mode|role|scopes|ts|token``
    """
    version = "v2" if nonce else "v1"
    parts: list[str] = [
        version,
        device_id,
        client_id,
        client_mode,
        role,
        ",".join(scopes),
        str(signed_at_ms),
        token or "",
    ]
    if nonce:
        parts.append(nonce)
    return "|".join(parts)


def _sign_payload(key: Ed25519PrivateKey, payload: str) -> str:
    """Sign the auth payload with Ed25519 and return base64url signature."""
    sig = key.sign(payload.encode("utf-8"))
    return _b64url(sig)


# -- Gateway client ---------------------------------------------------------


class GatewayConnectionError(Exception):
    """Failed to connect or authenticate with the OpenClaw Gateway."""


class GatewayClient:
    """Manages WebSocket connection to an OpenClaw Gateway (node role).

    When *on_request* is provided, incoming ``node.invoke.request`` events
    are dispatched to that callback and the result is sent back as a
    ``node.invoke.result`` request frame.  Without *on_request*, the client
    operates in outbound-only mode (still connects as a node but ignores
    inbound commands).
    """

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        client_id: str = "node-host",
        client_version: str | None = None,
        display_name: str | None = None,
        device_family: str | None = None,
        model_identifier: str | None = None,
        capabilities: NodeCapabilities | None = None,
        on_request: Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]] | None = None,
    ) -> None:
        self._url = url
        self._token = token
        self._client_id = client_id
        if client_version is None:
            from tescmd import __version__

            client_version = f"tescmd/{__version__}"
        self._client_version = client_version
        self._display_name = display_name
        self._device_family = device_family or platform.system().lower()
        self._model_identifier = model_identifier or "tescmd"
        self._capabilities = capabilities
        self._on_request = on_request
        self._ws: ClientConnection | None = None
        self._connected = False
        self._send_count = 0
        self._recv_count = 0
        self._drop_count = 0
        self._msg_id = 0
        self._node_id: str | None = None
        self._recv_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def send_count(self) -> int:
        return self._send_count

    @property
    def recv_count(self) -> int:
        return self._recv_count

    @property
    def drop_count(self) -> int:
        return self._drop_count

    def _next_id(self) -> str:
        """Return an incrementing message ID for request frames."""
        self._msg_id += 1
        return str(self._msg_id)

    async def connect(self) -> None:
        """Connect to the gateway and complete the handshake.

        Passes the auth token as a Bearer header during the HTTP upgrade
        so gateways that enforce authentication at the transport layer
        accept the connection before the OpenClaw handshake begins.

        Raises :class:`GatewayConnectionError` on failure.
        """
        await self._establish_connection()

        if self._on_request is not None:
            self._recv_task = asyncio.create_task(self._receive_loop())
            logger.info("Inbound receive loop started")

    async def _establish_connection(self) -> None:
        """Open WebSocket and complete the handshake.

        This is the low-level connection method used by both initial
        :meth:`connect` and automatic reconnection.  It does **not**
        start the receive loop — that is the caller's responsibility.

        Raises :class:`GatewayConnectionError` on failure.
        """
        import contextlib

        import websockets.asyncio.client as ws_client
        from websockets.exceptions import ConnectionClosed

        # Clean up any stale WebSocket from a previous connection.
        if self._ws is not None:
            with contextlib.suppress(ConnectionClosed, OSError):
                await self._ws.close()
            self._ws = None

        headers: dict[str, str] = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            self._ws = await ws_client.connect(
                self._url,
                additional_headers=headers,
            )
        except Exception as exc:
            raise GatewayConnectionError(
                f"Failed to connect to gateway at {self._url}: {exc}"
            ) from exc

        try:
            await self._handshake()
        except GatewayConnectionError:
            raise
        except Exception as exc:
            raise GatewayConnectionError(f"Handshake failed with {self._url}: {exc}") from exc

        self._connected = True
        logger.info("Connected to OpenClaw Gateway at %s", self._url)

    async def _handshake(self) -> None:
        """Complete the OpenClaw connect challenge → hello-ok handshake.

        Protocol:
          1. Receive  ``{type:"event", event:"connect.challenge", ...}``
          2. Sign     pipe-delimited auth payload with Ed25519 device key
          3. Send     ``{type:"req", method:"connect", params:{...}}``
          4. Receive  ``{type:"event", event:"hello-ok", ...}``
        """
        assert self._ws is not None

        # 1. Receive challenge event
        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        msg = json.loads(raw)
        logger.debug("Gateway challenge: %s", raw)

        event_name = msg.get("event", "")
        if event_name != "connect.challenge":
            raise GatewayConnectionError(
                f"Expected connect.challenge, got: {event_name or msg.get('type', 'unknown')}"
            )

        payload = msg.get("payload") or msg.get("data") or {}
        nonce = payload.get("nonce", "")

        # 2. Build signed device auth
        device_key = _ensure_device_key()
        dev_id = _device_id(device_key)
        self._node_id = dev_id
        signed_at_ms = int(datetime.now(UTC).timestamp() * 1000)
        scopes = ["node.telemetry", "node.command"]

        auth_payload = _build_auth_payload(
            device_id=dev_id,
            client_id=self._client_id,
            client_mode="node",
            role="node",
            scopes=scopes,
            signed_at_ms=signed_at_ms,
            token=self._token,
            nonce=nonce or None,
        )
        signature = _sign_payload(device_key, auth_payload)

        # 3. Send connect request (typed frame)
        params: dict[str, Any] = {
            "role": "node",
            "scopes": scopes,
            "minProtocol": _PROTOCOL_VERSION,
            "maxProtocol": _PROTOCOL_VERSION,
            "client": {
                "id": self._client_id,
                "version": self._client_version,
                "platform": "tescmd",
                "deviceFamily": self._device_family,
                "modelIdentifier": self._model_identifier,
                "mode": "node",
                **({"displayName": self._display_name} if self._display_name else {}),
            },
            "device": {
                "id": dev_id,
                "publicKey": _public_key_raw_b64url(device_key),
                "signature": signature,
                "signedAt": signed_at_ms,
                "nonce": nonce,
            },
        }
        if self._token:
            params["auth"] = {"token": self._token}
        if self._capabilities is not None:
            cap_params = self._capabilities.to_connect_params()
            logger.info(
                "Node capabilities: caps=%d commands=%d permissions=%d — commands=%s",
                len(cap_params.get("caps", [])),
                len(cap_params.get("commands", [])),
                len(cap_params.get("permissions", {})),
                cap_params.get("commands", []),
            )
            params.update(cap_params)

        connect_msg: dict[str, Any] = {
            "type": "req",
            "id": self._next_id(),
            "method": "connect",
            "params": params,
        }
        logger.debug("Gateway connect: %s", json.dumps(connect_msg))
        await self._ws.send(json.dumps(connect_msg))

        # 4. Receive hello-ok (event) or error (res)
        raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
        msg = json.loads(raw)
        logger.debug("Gateway response: %s", raw)

        msg_type = msg.get("type", "")
        event_name = msg.get("event", "")

        # Success: {type:"event", event:"hello-ok"} or {type:"res", ok:true}
        if event_name == "hello-ok":
            return
        if msg_type == "res" and msg.get("ok", False):
            return

        # Error: {type:"res", ok:false, error:...}
        if msg_type == "res" and not msg.get("ok", False):
            error = msg.get("error", "unknown error")
            raise GatewayConnectionError(f"Handshake failed: {error}")

        raise GatewayConnectionError(
            f"Unexpected handshake response: type={msg_type}, event={event_name}"
        )

    # -- Inbound request handling -----------------------------------------------

    async def _receive_loop(self) -> None:
        """Listen for inbound frames from the gateway with auto-reconnect.

        The gateway sends commands as ``node.invoke.request`` events::

            {type: "event", event: "node.invoke.request",
             payload: {id, nodeId, command, paramsJSON, timeoutMs}}

        The node responds with a ``node.invoke.result`` request::

            {type: "req", method: "node.invoke.result",
             params: {id, nodeId, ok, payloadJSON|error}}

        On disconnect, the loop automatically attempts to reconnect with
        exponential backoff before resuming.
        """
        from websockets.exceptions import ConnectionClosed

        while True:
            try:
                assert self._ws is not None
                logger.info("Receive loop running — waiting for inbound frames")
                async for raw in self._ws:
                    try:
                        msg = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning("Received non-JSON frame — ignoring")
                        continue

                    msg_type = msg.get("type", "")
                    event_name = msg.get("event", "")

                    logger.debug(
                        "Recv frame: type=%s event=%s method=%s id=%s",
                        msg_type,
                        event_name,
                        msg.get("method", ""),
                        msg.get("id", ""),
                    )

                    if msg_type == "event" and event_name == "node.invoke.request":
                        await self._handle_invoke(msg.get("payload") or {})
                    elif msg_type == "event" and event_name not in ("ping", "pong", ""):
                        logger.debug("Unhandled event: %s", event_name)
                # Iterator exhausted normally (clean close)
                logger.info("Gateway closed connection cleanly")
                self._connected = False
            except asyncio.CancelledError:
                logger.debug("Receive loop cancelled")
                raise
            except ConnectionClosed as exc:
                code = exc.rcvd.code if exc.rcvd else "?"
                reason = exc.rcvd.reason if exc.rcvd else "unknown"
                logger.info("Gateway connection closed (code=%s reason=%s)", code, reason)
                self._connected = False
            except Exception:
                logger.warning("Receive loop error", exc_info=True)
                self._connected = False

            # Attempt reconnect with backoff
            if not await self._try_reconnect():
                logger.error("Reconnection failed — receive loop exiting")
                break

    async def _try_reconnect(self) -> bool:
        """Attempt to re-establish the gateway connection with exponential backoff.

        Returns ``True`` on success, ``False`` after exhausting all attempts.
        Unlimited retries — runs until reconnected or cancelled.
        """
        try:
            await _retry_with_backoff(
                self._establish_connection,
                label=f"Reconnecting to {self._url}",
            )
            logger.info("Reconnected to OpenClaw Gateway")
            return True
        except GatewayConnectionError:
            return False

    async def _handle_invoke(self, payload: dict[str, Any]) -> None:
        """Handle a ``node.invoke.request`` event from the gateway."""
        invoke_id = payload.get("id", "")
        command = payload.get("command", "")
        params_json = payload.get("paramsJSON", "{}")
        logger.info("Invoke request: id=%s command=%s", invoke_id, command)

        if not self._on_request:
            await self._send_invoke_result(invoke_id, ok=False, error="no handler configured")
            return

        self._recv_count += 1

        # Parse the stringified params
        try:
            params = json.loads(params_json) if params_json else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Malformed paramsJSON for invoke %s (command=%s) — using empty params",
                invoke_id,
                command,
            )
            params = {}

        # Build the message dict the dispatcher expects
        dispatch_msg: dict[str, Any] = {
            "method": command,
            "params": params,
            "id": invoke_id,
        }

        try:
            result = await asyncio.wait_for(self._on_request(dispatch_msg), timeout=30)
            if result is None:
                await self._send_invoke_result(
                    invoke_id, ok=False, error=f"unknown command: {command}"
                )
            else:
                await self._send_invoke_result(invoke_id, ok=True, result_payload=result)
        except TimeoutError:
            await self._send_invoke_result(invoke_id, ok=False, error="handler timeout (30s)")
        except Exception as exc:
            logger.warning("Invoke handler error for %s", command, exc_info=True)
            await self._send_invoke_result(invoke_id, ok=False, error=str(exc))

    async def _send_invoke_result(
        self,
        invoke_id: str,
        *,
        ok: bool,
        result_payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Send a ``node.invoke.result`` request back to the gateway."""
        if self._ws is None:
            logger.warning("Cannot send invoke result for %s — not connected", invoke_id)
            return

        params: dict[str, Any] = {
            "id": invoke_id,
            "nodeId": self._node_id or "",
            "ok": ok,
        }
        if ok and result_payload is not None:
            params["payloadJSON"] = json.dumps(result_payload, default=str)
        if not ok and error is not None:
            params["error"] = {"message": error}

        frame: dict[str, Any] = {
            "type": "req",
            "id": self._next_id(),
            "method": "node.invoke.result",
            "params": params,
        }

        wire = json.dumps(frame)
        logger.info("Sending invoke result: %s", wire[:500])
        try:
            await self._ws.send(wire)
        except Exception:
            logger.warning("Failed to send invoke result for %s", invoke_id, exc_info=True)
            self._connected = False

    # -- Outbound event sending -----------------------------------------------

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send an event to the gateway as a typed request frame.

        Wraps the event dict in the ``{type:"req", id, method, params}``
        envelope if it doesn't already have a ``type`` field.

        Silently drops the event if not connected. Never raises on send
        failure — logs and marks as disconnected instead.
        """
        if not self._connected or self._ws is None:
            self._drop_count += 1
            if self._drop_count == 1 or self._drop_count % 100 == 0:
                logger.warning("Event dropped (not connected) — total drops: %d", self._drop_count)
            return

        if "type" not in event:
            event = {
                "type": "req",
                "id": self._next_id(),
                **event,
            }

        try:
            await self._ws.send(json.dumps(event))
            self._send_count += 1
        except Exception:
            self._drop_count += 1
            logger.warning(
                "Send failed — marking disconnected (total drops: %d)", self._drop_count
            )
            self._connected = False

    async def close(self) -> None:
        """Close the gateway connection gracefully."""
        import contextlib

        from websockets.exceptions import ConnectionClosed

        self._connected = False
        if self._recv_task is not None and not self._recv_task.done():
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._recv_task
            self._recv_task = None
        if self._ws is not None:
            with contextlib.suppress(ConnectionClosed, OSError):
                await self._ws.close()
            self._ws = None

    async def connect_with_backoff(self, *, max_attempts: int = 0) -> None:
        """Connect with exponential backoff retry.

        Parameters
        ----------
        max_attempts:
            Maximum connection attempts. ``0`` means infinite.
        """
        await _retry_with_backoff(
            self.connect,
            label=f"Connecting to {self._url}",
            max_attempts=max_attempts,
        )
