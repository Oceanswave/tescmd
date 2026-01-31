"""Tests for the TailscaleManager."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tescmd.api.errors import TailscaleError
from tescmd.telemetry.tailscale import TailscaleManager


def _make_proc(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> AsyncMock:
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    return proc


def _status_json(
    backend_state: str = "Running",
    dns_name: str = "box.tail12345.ts.net.",
) -> str:
    return json.dumps(
        {
            "BackendState": backend_state,
            "Self": {"DNSName": dns_name},
        }
    )


class TestCheckAvailable:
    async def test_not_installed(self) -> None:
        with (
            patch("tescmd.telemetry.tailscale.shutil.which", return_value=None),
            pytest.raises(TailscaleError, match="Tailscale CLI not found"),
        ):
            await TailscaleManager().check_available()

    async def test_installed(self) -> None:
        with patch(
            "tescmd.telemetry.tailscale.shutil.which",
            return_value="/usr/bin/tailscale",
        ):
            ts = TailscaleManager()
            await ts.check_available()


class TestCheckRunning:
    async def test_not_running(self) -> None:
        proc = _make_proc(returncode=1, stderr="not running")
        with (
            patch("asyncio.create_subprocess_exec", return_value=proc),
            pytest.raises(TailscaleError, match="not running"),
        ):
            await TailscaleManager().check_running()

    async def test_bad_state(self) -> None:
        proc = _make_proc(stdout=_status_json(backend_state="NeedsLogin"))
        with (
            patch("asyncio.create_subprocess_exec", return_value=proc),
            pytest.raises(TailscaleError, match="NeedsLogin"),
        ):
            await TailscaleManager().check_running()

    async def test_running(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(stdout=_status_json())
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            status = await ts.check_running()
            assert status["BackendState"] == "Running"


class TestGetHostname:
    async def test_hostname_extracted(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(
            stdout=_status_json(dns_name="mybox.tail99.ts.net."),
        )
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            hostname = await ts.get_hostname()
            assert hostname == "mybox.tail99.ts.net"

    async def test_no_dns_name(self) -> None:
        status = json.dumps(
            {
                "BackendState": "Running",
                "Self": {"DNSName": ""},
            }
        )
        proc = _make_proc(stdout=status)
        with (
            patch("asyncio.create_subprocess_exec", return_value=proc),
            pytest.raises(TailscaleError, match="hostname"),
        ):
            await TailscaleManager().get_hostname()


class TestCheckFunnelAvailable:
    async def test_funnel_available(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(returncode=0, stdout="")
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await ts.check_funnel_available() is True

    async def test_funnel_not_available(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(returncode=1, stderr="funnel not enabled in ACL")
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await ts.check_funnel_available() is False

    async def test_funnel_error_returns_false(self) -> None:
        ts = TailscaleManager()
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("tailscale"),
        ):
            assert await ts.check_funnel_available() is False


class TestServe:
    async def test_start_serve(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await ts.start_serve("/.well-known/", "/tmp/serve/.well-known/")
            # Verify the correct command was called
            args = mock_exec.call_args[0]
            assert "serve" in args
            assert "--set-path" in args
            assert "/.well-known/" in args

    async def test_start_serve_failure(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(returncode=1, stderr="permission denied")
        with (
            patch("asyncio.create_subprocess_exec", return_value=proc),
            pytest.raises(TailscaleError, match="Failed to start Tailscale serve"),
        ):
            await ts.start_serve("/.well-known/", "/tmp/serve/.well-known/")

    async def test_stop_serve(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await ts.stop_serve("/.well-known/")
            args = mock_exec.call_args[0]
            assert "off" in args

    async def test_stop_serve_already_stopped(self) -> None:
        """stop_serve does not raise even if the path is not being served."""
        ts = TailscaleManager()
        proc = _make_proc(returncode=1, stderr="not found")
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            # Should log warning but not raise
            await ts.stop_serve("/.well-known/")


class TestEnableFunnel:
    async def test_enable_funnel(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await ts.enable_funnel()
            args = mock_exec.call_args[0]
            assert "funnel" in args
            assert "443" in args

    async def test_enable_funnel_failure(self) -> None:
        ts = TailscaleManager()
        proc = _make_proc(returncode=1, stderr="ACL denies funnel")
        with (
            patch("asyncio.create_subprocess_exec", return_value=proc),
            pytest.raises(TailscaleError, match="Failed to enable Tailscale Funnel"),
        ):
            await ts.enable_funnel()


class TestFunnel:
    async def test_start_funnel(self) -> None:
        ts = TailscaleManager()
        status_proc = _make_proc(stdout=_status_json())
        funnel_proc = _make_proc(returncode=0, stdout="")

        async def _mock(*args: Any, **kw: Any) -> AsyncMock:
            if "funnel" in args:
                return funnel_proc
            return status_proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock):
            url = await ts.start_funnel(55123)
            assert url == "https://box.tail12345.ts.net"
            assert ts._funnel_started is True

    async def test_start_funnel_failure(self) -> None:
        ts = TailscaleManager()
        status_proc = _make_proc(stdout=_status_json())
        fail_proc = _make_proc(returncode=1, stderr="funnel not enabled")

        async def _mock(*args: Any, **kw: Any) -> AsyncMock:
            if "funnel" in args:
                return fail_proc
            return status_proc

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_mock),
            pytest.raises(TailscaleError, match="Failed to start"),
        ):
            await ts.start_funnel(55123)

    async def test_stop_funnel_noop(self) -> None:
        ts = TailscaleManager()
        await ts.stop_funnel()

    async def test_stop_funnel(self) -> None:
        ts = TailscaleManager()
        ts._funnel_started = True
        ts._port = 55123
        stop_proc = _make_proc(returncode=0)
        with patch("asyncio.create_subprocess_exec", return_value=stop_proc):
            await ts.stop_funnel()
            assert ts._funnel_started is False
            assert ts._port is None


class TestGetCertPem:
    async def test_cert_retrieval(self) -> None:
        ts = TailscaleManager()
        status_proc = _make_proc(stdout=_status_json())
        cert_pem = "-----BEGIN CERTIFICATE-----\nABC\n-----END CERTIFICATE-----\n"

        async def _mock(*args: Any, **kw: Any) -> AsyncMock:
            if "cert" in args:
                args_list = list(args)
                idx = args_list.index("--cert-file") + 1
                Path(args_list[idx]).write_text(cert_pem)
                return _make_proc(returncode=0)
            return status_proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock):
            result = await ts.get_cert_pem()
            assert "BEGIN CERTIFICATE" in result

    async def test_cert_failure(self) -> None:
        ts = TailscaleManager()
        status_proc = _make_proc(stdout=_status_json())
        fail_proc = _make_proc(returncode=1, stderr="cert failed")

        async def _mock(*args: Any, **kw: Any) -> AsyncMock:
            if "cert" in args:
                return fail_proc
            return status_proc

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_mock),
            pytest.raises(TailscaleError, match="Failed to get"),
        ):
            await ts.get_cert_pem()


class TestTimeout:
    async def test_timeout_raises_tailscale_error(self) -> None:
        ts = TailscaleManager()

        async def _hanging(*args: Any, **kw: Any) -> AsyncMock:
            proc = AsyncMock()
            proc.returncode = None

            async def _wait() -> tuple[bytes, bytes]:
                await asyncio.sleep(100)
                return b"", b""

            proc.communicate = _wait
            return proc

        with (
            patch("asyncio.create_subprocess_exec", side_effect=_hanging),
            patch("tescmd.telemetry.tailscale._SUBPROCESS_TIMEOUT", 0.1),
            pytest.raises(TailscaleError, match="timed out"),
        ):
            await ts.check_running()
