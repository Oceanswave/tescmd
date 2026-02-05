"""Tests for port resolution and conflict handling in ``tescmd serve``."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import click
import pytest


class TestResolvePort:
    """Unit tests for ``_resolve_port()``."""

    def test_available_port_returned(self) -> None:
        """When the preferred port is free, return it unchanged."""
        from tescmd.cli.serve import _resolve_port

        # Use port 0 to let the OS pick a free port, then verify
        # _resolve_port returns it when it's actually free.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
        # Port is now released — _resolve_port should succeed.
        result = _resolve_port("127.0.0.1", free_port, auto_select=True)
        assert result == free_port

    def test_occupied_port_auto_selects(self) -> None:
        """When the port is in use and auto_select=True, return a different port."""
        from tescmd.cli.serve import _resolve_port

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            occupied_port = s.getsockname()[1]
            s.listen(1)

            result = _resolve_port("127.0.0.1", occupied_port, auto_select=True)
            assert result != occupied_port
            assert 1 <= result <= 65535

    def test_occupied_port_raises_when_explicit(self) -> None:
        """When the port is in use and auto_select=False, raise UsageError."""
        from tescmd.cli.serve import _resolve_port

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            occupied_port = s.getsockname()[1]
            s.listen(1)

            with pytest.raises(click.UsageError, match="already in use"):
                _resolve_port("127.0.0.1", occupied_port, auto_select=False)

    def test_usage_error_suggests_next_port(self) -> None:
        """The error message should suggest the next port number."""
        from tescmd.cli.serve import _resolve_port

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", 0))
            occupied_port = s.getsockname()[1]
            s.listen(1)

            with pytest.raises(click.UsageError, match=str(occupied_port + 1)):
                _resolve_port("127.0.0.1", occupied_port, auto_select=False)


class TestSafeUvicornServe:
    """Unit tests for ``_safe_uvicorn_serve()``."""

    @pytest.mark.asyncio
    async def test_system_exit_becomes_os_error(self) -> None:
        """SystemExit from uvicorn should be caught and re-raised as OSError."""
        from tescmd.cli.serve import _safe_uvicorn_serve

        mock_server = MagicMock()
        mock_server.serve = AsyncMock(side_effect=SystemExit(1))

        with pytest.raises(OSError, match="MCP server failed to start on port 8080"):
            await _safe_uvicorn_serve(mock_server, 8080)

    @pytest.mark.asyncio
    async def test_normal_completion_passes_through(self) -> None:
        """When serve() completes normally, no error is raised."""
        from tescmd.cli.serve import _safe_uvicorn_serve

        mock_server = MagicMock()
        mock_server.serve = AsyncMock(return_value=None)

        # Should not raise
        await _safe_uvicorn_serve(mock_server, 8080)
        mock_server.serve.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_exceptions_propagate(self) -> None:
        """Non-SystemExit exceptions should propagate unchanged."""
        from tescmd.cli.serve import _safe_uvicorn_serve

        mock_server = MagicMock()
        mock_server.serve = AsyncMock(side_effect=RuntimeError("something else"))

        with pytest.raises(RuntimeError, match="something else"):
            await _safe_uvicorn_serve(mock_server, 8080)


class TestMCPServerRunHttpSystemExit:
    """Verify MCPServer.run_http() catches SystemExit."""

    @pytest.mark.asyncio
    async def test_system_exit_becomes_os_error(self) -> None:
        """SystemExit from uvicorn in run_http() should become OSError."""
        from unittest.mock import patch

        from tescmd.mcp.server import MCPServer

        server = MCPServer(client_id="test-id", client_secret="test-secret")

        mock_uvi_server = MagicMock()
        mock_uvi_server.serve = AsyncMock(side_effect=SystemExit(1))

        mock_uvicorn = MagicMock()
        mock_uvicorn.Config.return_value = MagicMock()
        mock_uvicorn.Server.return_value = mock_uvi_server

        with (
            patch.dict("sys.modules", {"uvicorn": mock_uvicorn}),
            pytest.raises(OSError, match="MCP server failed to start on port 9999"),
        ):
            await server.run_http(host="127.0.0.1", port=9999)
