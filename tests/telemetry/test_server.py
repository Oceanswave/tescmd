"""Tests for TelemetryServer — WebSocket server integration."""

from __future__ import annotations

import asyncio

from tescmd.telemetry.decoder import TelemetryDecoder, TelemetryFrame
from tescmd.telemetry.server import TelemetryServer

# We reuse test payload helpers from test_decoder
from tests.telemetry.test_decoder import (
    _encode_datum,
    _encode_int_value,
    _encode_payload,
)


class TestTelemetryServer:
    async def test_start_and_stop(self) -> None:
        frames: list[TelemetryFrame] = []

        async def on_frame(frame: TelemetryFrame) -> None:
            frames.append(frame)

        server = TelemetryServer(port=0, decoder=TelemetryDecoder(), on_frame=on_frame)
        # Port 0 = OS picks a free port — but websockets may not support it.
        # Use a high random port instead.
        server._port = 59871
        await server.start()
        assert server._server is not None
        await server.stop()
        assert server._server is None

    async def test_receive_frame(self) -> None:
        import websockets.asyncio.client as ws_client

        frames: list[TelemetryFrame] = []

        async def on_frame(frame: TelemetryFrame) -> None:
            frames.append(frame)

        port = 59872
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=on_frame)
        await server.start()

        try:
            datum = _encode_datum(8, _encode_int_value(72))
            payload = _encode_payload([datum], vin="TEST_VIN")

            async with ws_client.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(payload)
                # Give server time to process
                await asyncio.sleep(0.1)

            assert len(frames) == 1
            assert frames[0].vin == "TEST_VIN"
            assert frames[0].data[0].field_name == "BatteryLevel"
            assert frames[0].data[0].value == 72
            assert server.frame_count == 1
        finally:
            await server.stop()

    async def test_malformed_frame_skipped(self) -> None:
        import websockets.asyncio.client as ws_client

        frames: list[TelemetryFrame] = []

        async def on_frame(frame: TelemetryFrame) -> None:
            frames.append(frame)

        port = 59873
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=on_frame)
        await server.start()

        try:
            async with ws_client.connect(f"ws://127.0.0.1:{port}") as ws:
                # Send invalid protobuf
                await ws.send(b"\xff\xff\xff")
                await asyncio.sleep(0.1)

                # Send valid frame after
                datum = _encode_datum(3, _encode_int_value(85))
                payload = _encode_payload([datum])
                await ws.send(payload)
                await asyncio.sleep(0.1)

            # The valid frame should still be processed
            assert len(frames) >= 1
            assert server.frame_count >= 1
        finally:
            await server.stop()

    async def test_text_frame_ignored(self) -> None:
        import websockets.asyncio.client as ws_client

        frames: list[TelemetryFrame] = []

        async def on_frame(frame: TelemetryFrame) -> None:
            frames.append(frame)

        port = 59874
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=on_frame)
        await server.start()

        try:
            async with ws_client.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send("text message")
                await asyncio.sleep(0.1)

            assert len(frames) == 0
        finally:
            await server.stop()

    def test_initial_counts(self) -> None:
        async def noop(frame: TelemetryFrame) -> None:
            pass

        server = TelemetryServer(port=0, decoder=TelemetryDecoder(), on_frame=noop)
        assert server.connection_count == 0
        assert server.frame_count == 0
