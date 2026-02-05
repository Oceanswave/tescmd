"""Tests for GatewayClient WebSocket protocol."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tescmd.openclaw.config import NodeCapabilities
from tescmd.openclaw.gateway import (
    GatewayClient,
    GatewayConnectionError,
    _build_auth_payload,
    _ensure_device_key,
    _public_key_raw_b64url,
    _sign_payload,
)


def _challenge(nonce: str = "abc123") -> str:
    """Build a typed connect.challenge event."""
    return json.dumps(
        {
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": nonce, "ts": 1737264000000},
        }
    )


def _hello_ok() -> str:
    return json.dumps({"type": "event", "event": "hello-ok"})


class TestDeviceIdentity:
    def test_ensure_device_key_generates_ed25519(self, tmp_path: object) -> None:
        """Device key is Ed25519."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        with patch("tescmd.openclaw.gateway._device_key_dir", return_value=tmp_path):
            key = _ensure_device_key()
            assert isinstance(key, Ed25519PrivateKey)

    def test_ensure_device_key_reuses_existing(self, tmp_path: object) -> None:
        with patch("tescmd.openclaw.gateway._device_key_dir", return_value=tmp_path):
            key1 = _ensure_device_key()
            key2 = _ensure_device_key()
            assert _public_key_raw_b64url(key1) == _public_key_raw_b64url(key2)

    def test_public_key_is_32_bytes_b64url(self, tmp_path: object) -> None:
        import base64

        with patch("tescmd.openclaw.gateway._device_key_dir", return_value=tmp_path):
            key = _ensure_device_key()
            b64 = _public_key_raw_b64url(key)
            # Base64url without padding for 32 bytes = 43 chars
            raw = base64.urlsafe_b64decode(b64 + "=")
            assert len(raw) == 32

    def test_sign_and_verify_payload(self, tmp_path: object) -> None:
        """Signature is valid Ed25519."""
        import base64

        with patch("tescmd.openclaw.gateway._device_key_dir", return_value=tmp_path):
            key = _ensure_device_key()
            payload = "v2|dev|cli|backend|node|node.telemetry,node.command|1000||nonce"
            sig_b64 = _sign_payload(key, payload)
            # Restore base64url padding before decoding
            padded = sig_b64 + "=" * (-len(sig_b64) % 4)
            sig_bytes = base64.urlsafe_b64decode(padded)

            pub = key.public_key()
            # Should not raise
            pub.verify(sig_bytes, payload.encode("utf-8"))


class TestAuthPayload:
    def test_v2_with_nonce(self) -> None:
        p = _build_auth_payload(
            device_id="dev1",
            client_id="cli",
            client_mode="node",
            role="node",
            scopes=["node.telemetry", "node.command"],
            signed_at_ms=1000,
            token="tok",
            nonce="abc",
        )
        assert p == "v2|dev1|cli|node|node|node.telemetry,node.command|1000|tok|abc"

    def test_v1_without_nonce(self) -> None:
        p = _build_auth_payload(
            device_id="dev1",
            client_id="cli",
            client_mode="node",
            role="node",
            scopes=["node.telemetry", "node.command"],
            signed_at_ms=1000,
            token=None,
            nonce=None,
        )
        assert p == "v1|dev1|cli|node|node|node.telemetry,node.command|1000|"


class TestGatewayHandshake:
    @pytest.mark.asyncio
    async def test_successful_handshake(self) -> None:
        """Simulate: challenge → connect → hello-ok."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", token="my-token", client_id="test")
        gw._ws = mock_ws
        await gw._handshake()

        send_call = mock_ws.send.call_args
        sent = json.loads(send_call[0][0])
        assert sent["type"] == "req"
        assert "id" in sent
        assert sent["method"] == "connect"

        p = sent["params"]
        assert p["role"] == "node"
        assert "node.telemetry" in p["scopes"]
        assert "node.command" in p["scopes"]
        assert p["minProtocol"] >= 3
        assert p["maxProtocol"] >= 3
        assert p["auth"]["token"] == "my-token"

        # Client block — uses the client_id from constructor
        assert p["client"]["id"] == "test"
        assert "tescmd" in p["client"]["version"]
        assert p["client"]["platform"] == "tescmd"
        assert p["client"]["mode"] == "node"
        # deviceFamily auto-detected from OS, modelIdentifier defaults to "tescmd"
        assert isinstance(p["client"]["deviceFamily"], str)
        assert len(p["client"]["deviceFamily"]) > 0
        assert p["client"]["modelIdentifier"] == "tescmd"
        # No displayName when not provided
        assert "displayName" not in p["client"]

        # Device identity — Ed25519
        assert "publicKey" in p["device"]
        assert "signature" in p["device"]
        assert isinstance(p["device"]["signedAt"], int)
        assert p["device"]["nonce"] == "abc123"
        assert "id" in p["device"]

        # nonce should NOT be at root level
        assert "nonce" not in p

    @pytest.mark.asyncio
    async def test_successful_handshake_res_ok(self) -> None:
        """Gateway may respond with {type:res, ok:true} instead of hello-ok."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                _challenge(),
                json.dumps({"type": "res", "id": "1", "ok": True}),
            ]
        )
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", token="t")
        gw._ws = mock_ws
        await gw._handshake()  # should not raise

    @pytest.mark.asyncio
    async def test_successful_handshake_legacy_data_key(self) -> None:
        """Gateways may use 'data' instead of 'payload' — both should work."""
        mock_ws = AsyncMock()
        challenge = json.dumps(
            {
                "event": "connect.challenge",
                "data": {"nonce": "legacy-nonce"},
            }
        )
        mock_ws.recv = AsyncMock(side_effect=[challenge, _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", token="tok")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["params"]["device"]["signature"]  # non-empty
        assert sent["params"]["device"]["nonce"] == "legacy-nonce"

    @pytest.mark.asyncio
    async def test_no_token_omits_auth(self) -> None:
        """When no token is configured, auth block should be absent."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")  # no token
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert "auth" not in sent["params"]

    @pytest.mark.asyncio
    async def test_wrong_challenge_event_raises(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            return_value=json.dumps({"type": "event", "event": "wrong", "payload": {}})
        )

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws

        with pytest.raises(GatewayConnectionError, match=r"Expected connect\.challenge"):
            await gw._handshake()

    @pytest.mark.asyncio
    async def test_hello_rejected_raises(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                _challenge("x"),
                json.dumps(
                    {
                        "type": "res",
                        "id": "1",
                        "ok": False,
                        "error": "unauthorized",
                    }
                ),
            ]
        )
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws

        with pytest.raises(GatewayConnectionError, match="Handshake failed"):
            await gw._handshake()

    @pytest.mark.asyncio
    async def test_handshake_error_wrapped_in_connect(self) -> None:
        """Exceptions from _handshake are wrapped in GatewayConnectionError."""
        gw = GatewayClient("ws://test:1234")
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=ConnectionError("closed"))

        with patch("websockets.asyncio.client.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = mock_ws
            with pytest.raises(GatewayConnectionError, match="Handshake failed"):
                await gw.connect()


class TestDeviceKeyDir:
    def test_default_dir(self) -> None:
        """Without TESLA_CONFIG_DIR, key dir is under ~/.config/tescmd."""
        from tescmd.openclaw.gateway import _device_key_dir

        with patch.dict("os.environ", {}, clear=False):
            # Remove TESLA_CONFIG_DIR if present
            import os

            env = os.environ.copy()
            env.pop("TESLA_CONFIG_DIR", None)
            with patch.dict("os.environ", env, clear=True):
                d = _device_key_dir()
                assert d.name == "openclaw"
                assert "tescmd" in str(d.parent)

    def test_respects_tesla_config_dir(self, tmp_path: object) -> None:
        """TESLA_CONFIG_DIR env var overrides the default key directory."""
        from tescmd.openclaw.gateway import _device_key_dir

        with patch.dict("os.environ", {"TESLA_CONFIG_DIR": str(tmp_path)}):
            from pathlib import Path

            d = _device_key_dir()
            assert d == Path(str(tmp_path)) / "openclaw"


class TestGatewayDropCount:
    @pytest.mark.asyncio
    async def test_drop_count_increments_when_disconnected(self) -> None:
        gw = GatewayClient("ws://test:1234")
        gw._connected = False
        assert gw.drop_count == 0

        await gw.send_event({"method": "req:agent"})
        assert gw.drop_count == 1

        await gw.send_event({"method": "req:agent"})
        assert gw.drop_count == 2

    @pytest.mark.asyncio
    async def test_drop_count_increments_on_send_failure(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock(side_effect=ConnectionError("broken"))

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        gw._connected = True
        assert gw.drop_count == 0

        await gw.send_event({"method": "req:agent"})
        assert gw.drop_count == 1
        assert gw.is_connected is False

    @pytest.mark.asyncio
    async def test_drop_count_not_incremented_on_success(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        gw._connected = True

        await gw.send_event({"method": "req:agent"})
        assert gw.drop_count == 0
        assert gw.send_count == 1


class TestGatewaySendEvent:
    @pytest.mark.asyncio
    async def test_send_event_when_connected(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        gw._connected = True

        event = {"method": "req:agent", "params": {"event_type": "location"}}
        await gw.send_event(event)

        mock_ws.send.assert_called_once()
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["type"] == "req"
        assert "id" in sent
        assert sent["method"] == "req:agent"

    @pytest.mark.asyncio
    async def test_send_event_preserves_existing_type(self) -> None:
        """Events that already have a type field are not double-wrapped."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        gw._connected = True

        event = {
            "type": "req",
            "id": "custom-1",
            "method": "req:agent",
            "params": {},
        }
        await gw.send_event(event)

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["id"] == "custom-1"

    @pytest.mark.asyncio
    async def test_send_event_when_disconnected_is_noop(self) -> None:
        gw = GatewayClient("ws://test:1234")
        gw._connected = False
        await gw.send_event({"method": "req:agent"})

    @pytest.mark.asyncio
    async def test_send_failure_marks_disconnected(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock(side_effect=ConnectionError("broken pipe"))

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        gw._connected = True

        await gw.send_event({"method": "req:agent"})
        assert gw.is_connected is False

    @pytest.mark.asyncio
    async def test_send_count_increments(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        gw._connected = True

        assert gw.send_count == 0
        await gw.send_event({"method": "req:agent"})
        assert gw.send_count == 1
        await gw.send_event({"method": "req:agent"})
        assert gw.send_count == 2


class TestGatewayClose:
    @pytest.mark.asyncio
    async def test_close(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.close = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        gw._connected = True

        await gw.close()
        assert gw.is_connected is False
        mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        gw = GatewayClient("ws://test:1234")
        await gw.close()


class TestGatewayBackoff:
    @pytest.mark.asyncio
    async def test_max_attempts_reached_raises(self) -> None:
        gw = GatewayClient("ws://unreachable:1234")

        with (
            patch.object(gw, "connect", side_effect=GatewayConnectionError("fail")),
            patch(
                "tescmd.openclaw.gateway.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            pytest.raises(GatewayConnectionError),
        ):
            await gw.connect_with_backoff(max_attempts=3)

    @pytest.mark.asyncio
    async def test_backoff_succeeds_on_retry(self) -> None:
        gw = GatewayClient("ws://test:1234")
        call_count = 0

        async def _connect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise GatewayConnectionError("not yet")
            gw._connected = True

        with (
            patch.object(gw, "connect", side_effect=_connect),
            patch(
                "tescmd.openclaw.gateway.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await gw.connect_with_backoff(max_attempts=5)

        assert gw.is_connected is True
        assert call_count == 3


class TestConnectCancelsExistingRecvLoop:
    @pytest.mark.asyncio
    async def test_connect_cancels_old_recv_task(self) -> None:
        """Calling connect() while a receive loop is running cancels the old task."""
        gw = GatewayClient("ws://test:1234", on_request=AsyncMock())

        # Create a real task that blocks forever (simulates running recv loop)
        old_task = asyncio.create_task(asyncio.sleep(3600))
        gw._recv_task = old_task

        with patch.object(gw, "_establish_connection", new_callable=AsyncMock):
            await gw.connect()

        # Old task should have been cancelled and replaced
        assert old_task.cancelled()
        assert gw._recv_task is not old_task
        assert gw._recv_task is not None

    @pytest.mark.asyncio
    async def test_connect_skips_cancel_when_no_task(self) -> None:
        """connect() works fine when no previous recv task exists."""
        gw = GatewayClient("ws://test:1234", on_request=AsyncMock())
        assert gw._recv_task is None

        with patch.object(gw, "_establish_connection", new_callable=AsyncMock):
            await gw.connect()

        assert gw._recv_task is not None


class _MockWebSocket:
    """Minimal async-iterable WebSocket mock for receive loop tests."""

    def __init__(self, frames: list[str]) -> None:
        self._frames = frames
        self.send = AsyncMock()
        self.close = AsyncMock()

    def __aiter__(self) -> _MockWebSocket:
        self._idx = 0
        return self

    async def __anext__(self) -> str:
        if self._idx >= len(self._frames):
            raise StopAsyncIteration
        frame = self._frames[self._idx]
        self._idx += 1
        return frame


class _RaisingWebSocket:
    """WebSocket mock that raises on iteration (simulates ConnectionClosed)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.send = AsyncMock()
        self.close = AsyncMock()

    def __aiter__(self) -> _RaisingWebSocket:
        return self

    async def __anext__(self) -> str:
        raise self._exc


class TestHandshakeCapabilities:
    @pytest.mark.asyncio
    async def test_capabilities_in_connect_params(self) -> None:
        """Node capabilities are sent as caps/commands/permissions in connect params."""
        caps = NodeCapabilities(reads=["location.get"], writes=["door.lock"])
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", token="t", capabilities=caps)
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["params"]["caps"] == ["location", "door"]
        assert sent["params"]["commands"] == ["location.get", "door.lock"]
        assert sent["params"]["permissions"] == {"location.get": True, "door.lock": True}

    @pytest.mark.asyncio
    async def test_default_capabilities_sends_all_commands(self) -> None:
        """Default NodeCapabilities sends all advertised commands."""
        caps = NodeCapabilities()
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", token="t", capabilities=caps)
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        commands = sent["params"]["commands"]
        permissions = sent["params"]["permissions"]
        caps_list = sent["params"]["caps"]

        # 7 commands: 4 reads + 3 writes
        assert len(commands) == 7
        assert "location.get" in commands
        assert "telemetry.get" in commands
        assert "trigger.list" in commands
        assert "trigger.poll" in commands
        assert "system.run" in commands
        assert "trigger.create" in commands
        assert "trigger.delete" in commands

        # permissions must match commands 1:1
        assert len(permissions) == 7
        assert all(permissions[cmd] is True for cmd in commands)

        # caps: location, telemetry, trigger, system
        assert len(caps_list) == 4
        assert "location" in caps_list
        assert "telemetry" in caps_list
        assert "trigger" in caps_list
        assert "system" in caps_list

    @pytest.mark.asyncio
    async def test_no_capabilities_omits_caps(self) -> None:
        """Without capabilities, caps/commands/permissions are absent."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert "caps" not in sent["params"]
        assert "commands" not in sent["params"]
        assert "permissions" not in sent["params"]


class TestHandshakeDisplayName:
    @pytest.mark.asyncio
    async def test_display_name_included(self) -> None:
        """displayName is sent in the client block when provided."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", display_name="tescmd-0.2.0-5YJ3E1EA")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["params"]["client"]["displayName"] == "tescmd-0.2.0-5YJ3E1EA"

    @pytest.mark.asyncio
    async def test_display_name_omitted_when_none(self) -> None:
        """displayName is absent from client block when not provided."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert "displayName" not in sent["params"]["client"]


class TestHandshakeDeviceIdentification:
    @pytest.mark.asyncio
    async def test_platform_is_tescmd(self) -> None:
        """Platform field identifies as 'tescmd', not the local OS."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["params"]["client"]["platform"] == "tescmd"

    @pytest.mark.asyncio
    async def test_model_identifier_is_vin(self) -> None:
        """modelIdentifier carries the VIN when provided."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", model_identifier="5YJ3E1EA7PF123456")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["params"]["client"]["modelIdentifier"] == "5YJ3E1EA7PF123456"

    @pytest.mark.asyncio
    async def test_model_identifier_defaults_to_tescmd(self) -> None:
        """Without VIN, modelIdentifier falls back to 'tescmd'."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["params"]["client"]["modelIdentifier"] == "tescmd"

    @pytest.mark.asyncio
    async def test_device_family_auto_detected(self) -> None:
        """deviceFamily defaults to the OS name when not overridden."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        client = sent["params"]["client"]
        assert isinstance(client["deviceFamily"], str)
        assert len(client["deviceFamily"]) > 0

    @pytest.mark.asyncio
    async def test_custom_device_family(self) -> None:
        """Explicit device_family overrides auto-detection."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[_challenge(), _hello_ok()])
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", device_family="server")
        gw._ws = mock_ws
        await gw._handshake()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["params"]["client"]["deviceFamily"] == "server"


def _invoke_request(invoke_id: str, command: str, params: dict[str, Any] | None = None) -> str:
    """Build a ``node.invoke.request`` event frame for tests."""
    return json.dumps(
        {
            "type": "event",
            "event": "node.invoke.request",
            "payload": {
                "id": invoke_id,
                "nodeId": "test-node",
                "command": command,
                "paramsJSON": json.dumps(params or {}),
                "timeoutMs": 10000,
            },
        }
    )


class TestReceiveLoop:
    """Tests for the inbound receive loop with auto-reconnect.

    The receive loop runs ``while True`` — after the WebSocket closes it calls
    ``_try_reconnect()``.  All tests mock ``_try_reconnect`` to return ``False``
    so the loop exits cleanly after one pass.
    """

    @pytest.mark.asyncio
    async def test_receive_loop_dispatches_invoke(self) -> None:
        """Inbound node.invoke.request events are dispatched and responded to."""
        handler = AsyncMock(return_value={"result": True})
        mock_ws = _MockWebSocket([_invoke_request("42", "door.lock")])

        gw = GatewayClient("ws://test:1234", on_request=handler)
        gw._ws = mock_ws
        gw._connected = True
        gw._node_id = "my-node-id"

        with patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False):
            await gw._receive_loop()

        handler.assert_awaited_once()
        call_msg = handler.call_args[0][0]
        assert call_msg["method"] == "door.lock"
        assert call_msg["id"] == "42"

        # Verify node.invoke.result was sent
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["type"] == "req"
        assert sent["method"] == "node.invoke.result"
        p = sent["params"]
        assert p["id"] == "42"
        assert p["nodeId"] == "my-node-id"
        assert p["ok"] is True
        assert json.loads(p["payloadJSON"]) == {"result": True}

    @pytest.mark.asyncio
    async def test_receive_loop_sends_error_on_unknown_command(self) -> None:
        """Handler returning None → error invoke result."""
        handler = AsyncMock(return_value=None)
        mock_ws = _MockWebSocket([_invoke_request("99", "unknown.cmd")])

        gw = GatewayClient("ws://test:1234", on_request=handler)
        gw._ws = mock_ws
        gw._connected = True

        with patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False):
            await gw._receive_loop()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["method"] == "node.invoke.result"
        p = sent["params"]
        assert p["ok"] is False
        assert "unknown command" in p["error"]["message"]

    @pytest.mark.asyncio
    async def test_receive_loop_sends_error_on_handler_exception(self) -> None:
        """Handler raising → error invoke result."""
        handler = AsyncMock(side_effect=RuntimeError("boom"))
        mock_ws = _MockWebSocket([_invoke_request("7", "door.lock")])

        gw = GatewayClient("ws://test:1234", on_request=handler)
        gw._ws = mock_ws
        gw._connected = True

        with patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False):
            await gw._receive_loop()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["method"] == "node.invoke.result"
        p = sent["params"]
        assert p["ok"] is False
        assert "boom" in p["error"]["message"]

    @pytest.mark.asyncio
    async def test_receive_loop_handles_timeout(self) -> None:
        """Handler exceeding 30s → timeout error invoke result."""

        async def _slow_handler(msg: dict[str, Any]) -> dict[str, Any]:
            await asyncio.sleep(60)
            return {"result": True}

        mock_ws = _MockWebSocket([_invoke_request("T1", "slow.cmd")])

        gw = GatewayClient("ws://test:1234", on_request=_slow_handler)
        gw._ws = mock_ws
        gw._connected = True

        # Patch wait_for to raise TimeoutError immediately
        with (
            patch("tescmd.openclaw.gateway.asyncio.wait_for", side_effect=asyncio.TimeoutError),
            patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False),
        ):
            await gw._receive_loop()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["method"] == "node.invoke.result"
        p = sent["params"]
        assert p["ok"] is False
        assert "timeout" in p["error"]["message"]

    @pytest.mark.asyncio
    async def test_receive_loop_reconnects_on_close(self) -> None:
        """ConnectionClosed triggers _try_reconnect; disconnected if reconnect fails."""
        from websockets.exceptions import ConnectionClosed

        mock_ws = _RaisingWebSocket(ConnectionClosed(None, None))

        gw = GatewayClient("ws://test:1234", on_request=AsyncMock())
        gw._ws = mock_ws
        gw._connected = True

        mock_reconnect = AsyncMock(return_value=False)
        with patch.object(gw, "_try_reconnect", mock_reconnect):
            await gw._receive_loop()

        assert gw._connected is False
        mock_reconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_receive_loop_ignores_non_invoke_events(self) -> None:
        """Non-invoke events (heartbeat, etc.) are silently ignored."""
        handler = AsyncMock(return_value={"result": True})
        heartbeat = json.dumps({"type": "event", "event": "heartbeat"})
        plain_req = json.dumps({"type": "req", "id": "1", "method": "something"})
        invoke = _invoke_request("1", "door.lock")
        mock_ws = _MockWebSocket([heartbeat, plain_req, invoke])

        gw = GatewayClient("ws://test:1234", on_request=handler)
        gw._ws = mock_ws
        gw._connected = True

        with patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False):
            await gw._receive_loop()

        # Only the invoke request should have been dispatched
        handler.assert_awaited_once()
        call_msg = handler.call_args[0][0]
        assert call_msg["method"] == "door.lock"

    @pytest.mark.asyncio
    async def test_recv_count_increments(self) -> None:
        handler = AsyncMock(return_value={"ok": True})
        mock_ws = _MockWebSocket(
            [
                _invoke_request("1", "door.lock"),
                _invoke_request("2", "climate.on"),
            ]
        )

        gw = GatewayClient("ws://test:1234", on_request=handler)
        gw._ws = mock_ws
        gw._connected = True

        assert gw.recv_count == 0
        with patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False):
            await gw._receive_loop()
        assert gw.recv_count == 2

    @pytest.mark.asyncio
    async def test_invoke_parses_params_json(self) -> None:
        """paramsJSON is parsed and passed to the handler as params dict."""
        handler = AsyncMock(return_value={"ok": True})
        mock_ws = _MockWebSocket([_invoke_request("P1", "climate.set_temp", {"temp_c": 22.5})])

        gw = GatewayClient("ws://test:1234", on_request=handler)
        gw._ws = mock_ws
        gw._connected = True

        with patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False):
            await gw._receive_loop()

        call_msg = handler.call_args[0][0]
        assert call_msg["params"] == {"temp_c": 22.5}

    @pytest.mark.asyncio
    async def test_invoke_without_handler_sends_error(self) -> None:
        """Without on_request, invoke requests get an error response."""
        mock_ws = _MockWebSocket([_invoke_request("N1", "door.lock")])

        gw = GatewayClient("ws://test:1234")  # no on_request
        gw._ws = mock_ws
        gw._connected = True

        with patch.object(gw, "_try_reconnect", new_callable=AsyncMock, return_value=False):
            await gw._receive_loop()

        sent = json.loads(mock_ws.send.call_args[0][0])
        p = sent["params"]
        assert p["ok"] is False
        assert "no handler" in p["error"]["message"]

    @pytest.mark.asyncio
    async def test_reconnect_resumes_receiving(self) -> None:
        """After reconnect, the loop processes frames from the new WebSocket."""
        handler = AsyncMock(return_value={"ok": True})

        # First ws: one invoke, then closes
        ws1 = _MockWebSocket([_invoke_request("R1", "door.lock")])
        # Second ws: one invoke, then closes
        ws2 = _MockWebSocket([_invoke_request("R2", "climate.on")])

        gw = GatewayClient("ws://test:1234", on_request=handler)
        gw._ws = ws1
        gw._connected = True

        reconnect_count = 0

        async def _fake_reconnect() -> bool:
            nonlocal reconnect_count
            reconnect_count += 1
            if reconnect_count == 1:
                # First reconnect: swap to ws2
                gw._ws = ws2
                gw._connected = True
                return True
            # Second reconnect: stop the loop
            return False

        with patch.object(gw, "_try_reconnect", side_effect=_fake_reconnect):
            await gw._receive_loop()

        # Both invokes should have been dispatched
        assert handler.await_count == 2
        calls = [c[0][0]["method"] for c in handler.call_args_list]
        assert calls == ["door.lock", "climate.on"]


class TestGatewayCloseWithRecv:
    @pytest.mark.asyncio
    async def test_close_cancels_recv_task(self) -> None:
        """close() cancels the receive task."""
        gw = GatewayClient("ws://test:1234", on_request=AsyncMock())
        gw._connected = True
        gw._ws = AsyncMock()
        gw._ws.close = AsyncMock()

        # Create a task that will run forever
        async def _forever() -> None:
            await asyncio.sleep(3600)

        gw._recv_task = asyncio.create_task(_forever())
        await gw.close()

        assert gw._recv_task is None
        assert gw._connected is False


class TestReconnectCallback:
    @pytest.mark.asyncio
    async def test_reconnect_callback_called(self) -> None:
        """on_reconnect callback is awaited after successful reconnect in receive loop."""
        on_reconnect = AsyncMock()

        gw = GatewayClient("ws://test:1234", on_request=AsyncMock(), on_reconnect=on_reconnect)
        gw._ws = _MockWebSocket([])  # empty → iterator exhausts immediately
        gw._connected = True

        reconnect_count = 0

        async def _fake_reconnect() -> bool:
            nonlocal reconnect_count
            reconnect_count += 1
            if reconnect_count == 1:
                gw._ws = _MockWebSocket([])
                gw._connected = True
                return True
            return False

        with patch.object(gw, "_try_reconnect", side_effect=_fake_reconnect):
            await gw._receive_loop()

        on_reconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconnect_callback_failure_does_not_break_loop(self) -> None:
        """on_reconnect callback failure doesn't crash the receive loop."""
        on_reconnect = AsyncMock(side_effect=RuntimeError("callback boom"))

        gw = GatewayClient("ws://test:1234", on_request=AsyncMock(), on_reconnect=on_reconnect)
        gw._ws = _MockWebSocket([])
        gw._connected = True

        reconnect_count = 0

        async def _fake_reconnect() -> bool:
            nonlocal reconnect_count
            reconnect_count += 1
            if reconnect_count == 1:
                gw._ws = _MockWebSocket([])
                gw._connected = True
                return True
            return False

        with patch.object(gw, "_try_reconnect", side_effect=_fake_reconnect):
            await gw._receive_loop()

        # Callback was called despite the error, and the loop continued
        on_reconnect.assert_awaited_once()
        assert reconnect_count == 2  # Loop continued after callback failure
