"""Tests for Tailscale Funnel key deployment helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from tescmd.api.errors import TailscaleError
from tescmd.deploy import tailscale_serve as ts_serve

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# deploy_public_key_tailscale
# ---------------------------------------------------------------------------


class TestDeployPublicKeyTailscale:
    async def test_creates_directory_structure(self, tmp_path: Path) -> None:
        pem = "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----\n"
        key_path = await ts_serve.deploy_public_key_tailscale(pem, serve_dir=tmp_path)

        assert key_path.exists()
        assert key_path.read_text() == pem
        assert ".well-known" in str(key_path)
        assert "com.tesla.3p.public-key.pem" in str(key_path)

    async def test_overwrites_existing_key(self, tmp_path: Path) -> None:
        pem_old = "-----BEGIN PUBLIC KEY-----\nold\n-----END PUBLIC KEY-----\n"
        pem_new = "-----BEGIN PUBLIC KEY-----\nnew\n-----END PUBLIC KEY-----\n"

        await ts_serve.deploy_public_key_tailscale(pem_old, serve_dir=tmp_path)
        key_path = await ts_serve.deploy_public_key_tailscale(pem_new, serve_dir=tmp_path)

        assert key_path.read_text() == pem_new

    async def test_creates_nested_parents(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        key_path = await ts_serve.deploy_public_key_tailscale("pem-data", serve_dir=deep)
        assert key_path.exists()


# ---------------------------------------------------------------------------
# start_key_serving
# ---------------------------------------------------------------------------


class TestStartKeyServing:
    async def test_starts_serve_and_funnel(self, tmp_path: Path) -> None:
        # Create the expected directory structure
        well_known = tmp_path / ".well-known" / "appspecific"
        well_known.mkdir(parents=True)
        (well_known / "com.tesla.3p.public-key.pem").write_text("pem")

        with (
            patch.object(ts_serve.TailscaleManager, "check_available", new_callable=AsyncMock),
            patch.object(
                ts_serve.TailscaleManager,
                "get_hostname",
                new_callable=AsyncMock,
                return_value="mybox.tail99.ts.net",
            ),
            patch.object(
                ts_serve.TailscaleManager, "start_serve", new_callable=AsyncMock
            ) as mock_serve,
            patch.object(
                ts_serve.TailscaleManager, "enable_funnel", new_callable=AsyncMock
            ) as mock_funnel,
        ):
            hostname = await ts_serve.start_key_serving(serve_dir=tmp_path)

        assert hostname == "mybox.tail99.ts.net"
        mock_serve.assert_awaited_once()
        mock_funnel.assert_awaited_once()

    async def test_raises_when_serve_dir_missing(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(TailscaleError, match="Serve directory not found"):
            await ts_serve.start_key_serving(serve_dir=empty_dir)


# ---------------------------------------------------------------------------
# stop_key_serving
# ---------------------------------------------------------------------------


class TestStopKeyServing:
    async def test_stops_serve(self) -> None:
        with patch.object(
            ts_serve.TailscaleManager, "stop_serve", new_callable=AsyncMock
        ) as mock_stop:
            await ts_serve.stop_key_serving()
            mock_stop.assert_awaited_once_with("/.well-known/")


# ---------------------------------------------------------------------------
# is_tailscale_serve_ready
# ---------------------------------------------------------------------------


class TestIsTailscaleServeReady:
    async def test_all_checks_pass(self) -> None:
        with (
            patch.object(ts_serve.TailscaleManager, "check_available", new_callable=AsyncMock),
            patch.object(
                ts_serve.TailscaleManager,
                "check_running",
                new_callable=AsyncMock,
                return_value={"BackendState": "Running"},
            ),
            patch.object(
                ts_serve.TailscaleManager,
                "check_funnel_available",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            assert await ts_serve.is_tailscale_serve_ready() is True

    async def test_cli_not_available(self) -> None:
        with patch.object(
            ts_serve.TailscaleManager,
            "check_available",
            new_callable=AsyncMock,
            side_effect=TailscaleError("not found"),
        ):
            assert await ts_serve.is_tailscale_serve_ready() is False

    async def test_daemon_not_running(self) -> None:
        with (
            patch.object(ts_serve.TailscaleManager, "check_available", new_callable=AsyncMock),
            patch.object(
                ts_serve.TailscaleManager,
                "check_running",
                new_callable=AsyncMock,
                side_effect=TailscaleError("not running"),
            ),
        ):
            assert await ts_serve.is_tailscale_serve_ready() is False

    async def test_funnel_not_enabled(self) -> None:
        with (
            patch.object(ts_serve.TailscaleManager, "check_available", new_callable=AsyncMock),
            patch.object(
                ts_serve.TailscaleManager,
                "check_running",
                new_callable=AsyncMock,
                return_value={"BackendState": "Running"},
            ),
            patch.object(
                ts_serve.TailscaleManager,
                "check_funnel_available",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            assert await ts_serve.is_tailscale_serve_ready() is False


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


class TestGetKeyUrl:
    def test_returns_full_url(self) -> None:
        url = ts_serve.get_key_url("mybox.tail99.ts.net")
        assert url == (
            "https://mybox.tail99.ts.net/.well-known/appspecific/com.tesla.3p.public-key.pem"
        )


# ---------------------------------------------------------------------------
# validate_tailscale_key_url
# ---------------------------------------------------------------------------


class TestValidateTailscaleKeyUrl:
    async def test_valid_key(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tescmd.deploy.tailscale_serve.httpx.AsyncClient", return_value=mock_client):
            assert await ts_serve.validate_tailscale_key_url("mybox.tail99.ts.net") is True

    async def test_not_found(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tescmd.deploy.tailscale_serve.httpx.AsyncClient", return_value=mock_client):
            assert await ts_serve.validate_tailscale_key_url("mybox.tail99.ts.net") is False

    async def test_connection_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError(
                "Connection refused",
                request=httpx.Request("GET", "https://mybox.tail99.ts.net"),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("tescmd.deploy.tailscale_serve.httpx.AsyncClient", return_value=mock_client):
            assert await ts_serve.validate_tailscale_key_url("mybox.tail99.ts.net") is False


# ---------------------------------------------------------------------------
# wait_for_tailscale_deployment
# ---------------------------------------------------------------------------


class TestWaitForTailscaleDeployment:
    async def test_immediate_success(self) -> None:
        with patch(
            "tescmd.deploy.tailscale_serve.validate_tailscale_key_url",
            new_callable=AsyncMock,
            return_value=True,
        ):
            assert await ts_serve.wait_for_tailscale_deployment("host.ts.net") is True

    async def test_eventual_success(self) -> None:
        call_count = 0

        async def mock_validate(hostname: str) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 3

        with (
            patch(
                "tescmd.deploy.tailscale_serve.validate_tailscale_key_url",
                side_effect=mock_validate,
            ),
            patch("tescmd.deploy.tailscale_serve.asyncio.sleep", new_callable=AsyncMock),
        ):
            assert await ts_serve.wait_for_tailscale_deployment("host.ts.net") is True

    async def test_timeout(self) -> None:
        with (
            patch(
                "tescmd.deploy.tailscale_serve.validate_tailscale_key_url",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "tescmd.deploy.tailscale_serve.time.monotonic",
                side_effect=[0.0, 200.0],  # Already past deadline
            ),
        ):
            assert await ts_serve.wait_for_tailscale_deployment("bad.ts.net", timeout=10) is False
