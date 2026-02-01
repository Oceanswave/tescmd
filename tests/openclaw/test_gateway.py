"""Tests for GatewayClient WebSocket protocol."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tescmd.openclaw.gateway import GatewayClient, GatewayConnectionError


class TestGatewayHandshake:
    @pytest.mark.asyncio
    async def test_successful_handshake(self) -> None:
        """Simulate: challenge → connect → hello-ok."""
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"event": "connect.challenge", "data": {"nonce": "abc123"}}),
                json.dumps({"event": "hello-ok"}),
            ]
        )
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234", token="my-token", client_id="test")
        gw._ws = mock_ws
        await gw._handshake()

        # Verify connect message was sent
        send_call = mock_ws.send.call_args
        sent = json.loads(send_call[0][0])
        assert sent["method"] == "connect"
        assert sent["params"]["role"] == "operator"
        assert sent["params"]["nonce"] == "abc123"
        assert sent["params"]["token"] == "my-token"

    @pytest.mark.asyncio
    async def test_wrong_challenge_event_raises(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps({"event": "wrong", "data": {}}))

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws

        with pytest.raises(GatewayConnectionError, match=r"Expected connect\.challenge"):
            await gw._handshake()

    @pytest.mark.asyncio
    async def test_hello_rejected_raises(self) -> None:
        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"event": "connect.challenge", "data": {"nonce": "x"}}),
                json.dumps({"event": "error", "error": "unauthorized"}),
            ]
        )
        mock_ws.send = AsyncMock()

        gw = GatewayClient("ws://test:1234")
        gw._ws = mock_ws

        with pytest.raises(GatewayConnectionError, match="Handshake failed"):
            await gw._handshake()


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
        assert sent["method"] == "req:agent"

    @pytest.mark.asyncio
    async def test_send_event_when_disconnected_is_noop(self) -> None:
        gw = GatewayClient("ws://test:1234")
        gw._connected = False

        # Should not raise
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
        # Should not raise
        await gw.close()


class TestGatewayBackoff:
    @pytest.mark.asyncio
    async def test_max_attempts_reached_raises(self) -> None:
        gw = GatewayClient("ws://unreachable:1234")

        with (
            patch.object(gw, "connect", side_effect=GatewayConnectionError("fail")),
            patch("tescmd.openclaw.gateway.asyncio.sleep", new_callable=AsyncMock),
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
            patch("tescmd.openclaw.gateway.asyncio.sleep", new_callable=AsyncMock),
        ):
            await gw.connect_with_backoff(max_attempts=5)

        assert gw.is_connected is True
        assert call_count == 3
