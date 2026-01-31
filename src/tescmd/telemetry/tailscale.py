"""Tailscale integration for Fleet Telemetry Funnel setup.

Manages Tailscale presence checking, Funnel start/stop, and TLS
certificate retrieval — all via CLI subprocess (Funnel has no API).
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from tescmd.api.errors import TailscaleError

logger = logging.getLogger(__name__)

_SUBPROCESS_TIMEOUT = 15  # seconds


class TailscaleManager:
    """Manages Tailscale for Fleet Telemetry Funnel setup."""

    _port: int | None
    _funnel_started: bool

    def __init__(self) -> None:
        self._port = None
        self._funnel_started = False

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    async def check_available(self) -> None:
        """Verify ``tailscale`` CLI binary is on PATH.

        Raises :class:`TailscaleError` with install guidance if not found.
        """
        if shutil.which("tailscale") is None:
            platform = sys.platform
            if platform == "darwin":
                hint = "Install via: brew install tailscale"
            elif platform == "linux":
                hint = "Install via: curl -fsSL https://tailscale.com/install.sh | sh"
            else:
                hint = "Install from https://tailscale.com/download"
            raise TailscaleError(f"Tailscale CLI not found on PATH. {hint}")

    async def check_running(self) -> dict[str, Any]:
        """Verify the Tailscale daemon is running and authenticated.

        Returns the parsed ``tailscale status --json`` output.
        Raises :class:`TailscaleError` if the daemon is not running.
        """
        returncode, stdout, stderr = await self._run("tailscale", "status", "--json")
        if returncode != 0:
            raise TailscaleError(
                f"Tailscale is not running or not authenticated: {stderr.strip()}"
            )
        try:
            status: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise TailscaleError(f"Failed to parse tailscale status JSON: {exc}") from exc

        backend_state = status.get("BackendState", "")
        if backend_state != "Running":
            raise TailscaleError(
                f"Tailscale backend state is '{backend_state}', expected 'Running'. "
                "Run 'tailscale up' to authenticate."
            )
        return status

    async def get_hostname(self) -> str:
        """Extract the machine DNS name from ``tailscale status --json``.

        Returns e.g. ``'machine.tailnet.ts.net'`` (trailing dot stripped).
        """
        status = await self.check_running()

        # Self node info
        self_node = status.get("Self", {})
        dns_name: str = self_node.get("DNSName", "")
        if not dns_name:
            raise TailscaleError(
                "Could not determine Tailscale hostname. "
                "Ensure MagicDNS is enabled in your tailnet."
            )
        return dns_name.rstrip(".")

    async def check_funnel_available(self) -> bool:
        """Check if Funnel is enabled in tailnet ACL.

        Runs ``tailscale funnel status`` to probe availability.
        Returns False (without raising) if Funnel is not available.
        """
        try:
            returncode, _stdout, _stderr = await self._run(
                "tailscale",
                "funnel",
                "status",
            )
            return returncode == 0
        except TailscaleError:
            return False

    # ------------------------------------------------------------------
    # Serve management (static file hosting)
    # ------------------------------------------------------------------

    async def start_serve(self, path: str, target: str | Path) -> None:
        """Serve a local directory at a URL path prefix.

        Runs: ``tailscale serve --bg --set-path <path> <target>``

        Args:
            path: URL path prefix (e.g. ``/.well-known/``).
            target: Local directory to serve.
        """
        returncode, stdout, stderr = await self._run(
            "tailscale",
            "serve",
            "--bg",
            "--set-path",
            path,
            str(target),
        )
        if returncode != 0:
            msg = stderr.strip() or stdout.strip()
            raise TailscaleError(f"Failed to start Tailscale serve: {msg}")
        logger.info("Tailscale serve started: %s -> %s", path, target)

    async def stop_serve(self, path: str) -> None:
        """Remove a serve handler for a path.

        Runs: ``tailscale serve --bg --set-path <path> off``
        """
        returncode, stdout, stderr = await self._run(
            "tailscale",
            "serve",
            "--bg",
            "--set-path",
            path,
            "off",
        )
        if returncode != 0:
            logger.warning(
                "Failed to stop Tailscale serve for %s (may already be stopped): %s",
                path,
                stderr.strip() or stdout.strip(),
            )
        logger.info("Tailscale serve stopped for path: %s", path)

    async def enable_funnel(self) -> None:
        """Enable Funnel on port 443 (expose all serve handlers publicly).

        Runs: ``tailscale funnel --bg 443``
        """
        returncode, stdout, stderr = await self._run(
            "tailscale",
            "funnel",
            "--bg",
            "443",
        )
        if returncode != 0:
            msg = stderr.strip() or stdout.strip()
            raise TailscaleError(f"Failed to enable Tailscale Funnel: {msg}")
        logger.info("Tailscale Funnel enabled on port 443")

    # ------------------------------------------------------------------
    # Funnel management (port proxying for telemetry)
    # ------------------------------------------------------------------

    async def start_funnel(self, port: int) -> str:
        """Start Tailscale Funnel proxying to a local port.

        Args:
            port: Local port the WebSocket server is listening on.

        Returns:
            The public HTTPS URL (e.g. ``https://machine.tailnet.ts.net``).

        Raises:
            TailscaleError: If Funnel cannot be started.
        """
        hostname = await self.get_hostname()

        # tailscale funnel --bg <port> starts background proxy on 443
        returncode, stdout, stderr = await self._run(
            "tailscale",
            "funnel",
            "--bg",
            str(port),
        )
        if returncode != 0:
            msg = stderr.strip() or stdout.strip()
            raise TailscaleError(f"Failed to start Tailscale Funnel: {msg}")

        self._port = port
        self._funnel_started = True
        url = f"https://{hostname}"
        logger.info("Tailscale Funnel started: %s -> localhost:%d", url, port)
        return url

    async def stop_funnel(self) -> None:
        """Stop Tailscale Funnel. Idempotent — safe to call if not started."""
        if not self._funnel_started:
            return

        returncode, stdout, stderr = await self._run(
            "tailscale",
            "funnel",
            "--bg",
            "off",
        )
        if returncode != 0:
            logger.warning(
                "Failed to stop Tailscale Funnel (may already be stopped): %s",
                stderr.strip() or stdout.strip(),
            )
        self._funnel_started = False
        self._port = None
        logger.info("Tailscale Funnel stopped")

    async def get_cert_pem(self) -> str:
        """Retrieve the TLS certificate chain for the Funnel hostname.

        Uses ``tailscale cert`` to fetch/renew the cert, then reads the
        PEM file. Returns the PEM string for the Fleet Telemetry config
        ``ca`` field.
        """
        hostname = await self.get_hostname()

        with tempfile.TemporaryDirectory() as tmpdir:
            cert_path = Path(tmpdir) / f"{hostname}.crt"
            key_path = Path(tmpdir) / f"{hostname}.key"

            returncode, stdout, stderr = await self._run(
                "tailscale",
                "cert",
                "--cert-file",
                str(cert_path),
                "--key-file",
                str(key_path),
                hostname,
            )
            if returncode != 0:
                msg = stderr.strip() or stdout.strip()
                raise TailscaleError(f"Failed to get Tailscale cert: {msg}")

            if not cert_path.exists():
                raise TailscaleError(f"tailscale cert succeeded but {cert_path} not found")

            return cert_path.read_text()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _run(*args: str) -> tuple[int, str, str]:
        """Run a subprocess with timeout.

        Returns ``(returncode, stdout, stderr)``.

        Uses ``asyncio.create_subprocess_exec`` which passes arguments
        directly to the OS without shell interpretation (no injection risk).
        """
        logger.debug("Running: %s", " ".join(args))
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=_SUBPROCESS_TIMEOUT
            )
        except FileNotFoundError as exc:
            raise TailscaleError(f"Command not found: {args[0]}") from exc
        except TimeoutError as exc:
            raise TailscaleError(
                f"Command timed out after {_SUBPROCESS_TIMEOUT}s: {' '.join(args)}"
            ) from exc

        assert proc.returncode is not None
        return (
            proc.returncode,
            stdout_bytes.decode(errors="replace"),
            stderr_bytes.decode(errors="replace"),
        )
