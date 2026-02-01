"""Tests for TelemetryServer — WebSocket server integration."""

from __future__ import annotations

import asyncio

from tescmd.telemetry.decoder import TelemetryDecoder, TelemetryFrame
from tescmd.telemetry.server import TelemetryServer

# We reuse test payload helpers from test_decoder + Flatbuffers builder
from tests.telemetry.test_decoder import (
    _encode_datum,
    _encode_int_value,
    _encode_payload,
)
from tests.telemetry.test_flatbuf import build_flatbuf_envelope


class TestTelemetryServer:
    async def test_start_and_stop(self) -> None:
        frames: list[TelemetryFrame] = []

        async def on_frame(frame: TelemetryFrame) -> None:
            frames.append(frame)

        server = TelemetryServer(port=59870, decoder=TelemetryDecoder(), on_frame=on_frame)
        await server.start()
        assert server._mux_server is not None
        assert server._ws_server is not None
        await server.stop()
        assert server._mux_server is None
        assert server._ws_server is None

    async def test_receive_frame(self) -> None:
        import websockets.asyncio.client as ws_client

        frames: list[TelemetryFrame] = []

        async def on_frame(frame: TelemetryFrame) -> None:
            frames.append(frame)

        port = 59880
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=on_frame)
        await server.start()

        try:
            from tescmd.telemetry.protos import vehicle_data_pb2 as pb

            datum = _encode_datum(pb.BatteryLevel, _encode_int_value(72))
            pb_payload = _encode_payload([datum], vin="TEST_VIN")
            envelope = build_flatbuf_envelope(pb_payload, device_id=b"TEST_VIN")

            async with ws_client.connect(f"ws://127.0.0.1:{port}") as ws:
                await ws.send(envelope)
                # Give server time to process
                await asyncio.sleep(0.2)

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

        port = 59890
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=on_frame)
        await server.start()

        try:
            async with ws_client.connect(f"ws://127.0.0.1:{port}") as ws:
                # Send invalid protobuf
                await ws.send(b"\xff\xff\xff")
                await asyncio.sleep(0.2)

                # Send valid frame after
                from tescmd.telemetry.protos import vehicle_data_pb2 as pb

                datum = _encode_datum(pb.Soc, _encode_int_value(85))
                pb_payload = _encode_payload([datum])
                await ws.send(build_flatbuf_envelope(pb_payload))
                await asyncio.sleep(0.2)

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

        port = 59900
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

    async def test_head_request_returns_200(self) -> None:
        """HEAD requests (Tesla origin validation) get HTTP 200."""
        import httpx

        port = 59910
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=_noop)
        await server.start()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.head(f"http://127.0.0.1:{port}/")
                assert resp.status_code == 200
        finally:
            await server.stop()

    async def test_get_request_returns_200(self) -> None:
        """Plain GET requests (health check) get HTTP 200."""
        import httpx

        port = 59920
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=_noop)
        await server.start()

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}/")
                assert resp.status_code == 200
                assert b"tescmd" in resp.content
        finally:
            await server.stop()

    async def test_get_well_known_serves_public_key(self) -> None:
        """GET /.well-known/...public-key.pem serves the EC key when configured."""
        import httpx

        pem = "-----BEGIN PUBLIC KEY-----\nMFkwEwYH...test...\n-----END PUBLIC KEY-----\n"
        port = 59930
        server = TelemetryServer(
            port=port, decoder=TelemetryDecoder(), on_frame=_noop, public_key_pem=pem
        )
        await server.start()

        try:
            path = "/.well-known/appspecific/com.tesla.3p.public-key.pem"
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}{path}")
                assert resp.status_code == 200
                assert resp.text == pem
                assert resp.headers["content-type"] == "application/x-pem-file"
        finally:
            await server.stop()

    async def test_head_well_known_returns_key_length(self) -> None:
        """HEAD /.well-known/...public-key.pem returns correct Content-Length."""
        import httpx

        pem = "-----BEGIN PUBLIC KEY-----\nMFkwEwYH...test...\n-----END PUBLIC KEY-----\n"
        port = 59940
        server = TelemetryServer(
            port=port, decoder=TelemetryDecoder(), on_frame=_noop, public_key_pem=pem
        )
        await server.start()

        try:
            path = "/.well-known/appspecific/com.tesla.3p.public-key.pem"
            async with httpx.AsyncClient() as client:
                resp = await client.head(f"http://127.0.0.1:{port}{path}")
                assert resp.status_code == 200
                assert int(resp.headers["content-length"]) == len(pem.encode())
                assert resp.headers["content-type"] == "application/x-pem-file"
        finally:
            await server.stop()

    async def test_get_well_known_without_key_returns_generic(self) -> None:
        """GET /.well-known/ without a configured key returns generic 200."""
        import httpx

        port = 59950
        server = TelemetryServer(port=port, decoder=TelemetryDecoder(), on_frame=_noop)
        await server.start()

        try:
            path = "/.well-known/appspecific/com.tesla.3p.public-key.pem"
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://127.0.0.1:{port}{path}")
                assert resp.status_code == 200
                assert b"tescmd" in resp.content
        finally:
            await server.stop()


async def _noop(frame: TelemetryFrame) -> None:
    pass
