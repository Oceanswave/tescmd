"""Tailscale Funnel deployment helpers for Tesla Fleet API public keys.

Serves the public key at the Tesla-required ``.well-known`` path via
Tailscale's ``serve`` + ``funnel`` commands.  All Tailscale interaction
goes through :class:`~tescmd.telemetry.tailscale.TailscaleManager`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import httpx

from tescmd.api.errors import TailscaleError
from tescmd.telemetry.tailscale import TailscaleManager

logger = logging.getLogger(__name__)

WELL_KNOWN_PATH = ".well-known/appspecific/com.tesla.3p.public-key.pem"
DEFAULT_SERVE_DIR = Path("~/.config/tescmd/serve")

# Polling for deployment validation
DEFAULT_DEPLOY_TIMEOUT = 60  # seconds (faster than GitHub Pages)
POLL_INTERVAL = 3  # seconds


# ---------------------------------------------------------------------------
# Key file management
# ---------------------------------------------------------------------------


async def deploy_public_key_tailscale(
    public_key_pem: str,
    serve_dir: Path | None = None,
) -> Path:
    """Write the PEM key into the serve directory structure.

    Creates ``<serve_dir>/.well-known/appspecific/com.tesla.3p.public-key.pem``.

    Returns the path to the written key file.
    """
    base = (serve_dir or DEFAULT_SERVE_DIR).expanduser()
    key_path = base / WELL_KNOWN_PATH
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(public_key_pem)
    logger.info("Public key written to %s", key_path)
    return key_path


# ---------------------------------------------------------------------------
# Serve / Funnel lifecycle
# ---------------------------------------------------------------------------


async def start_key_serving(serve_dir: Path | None = None) -> str:
    """Start ``tailscale serve`` for ``.well-known`` and enable Funnel.

    Returns the public hostname (e.g. ``machine.tailnet.ts.net``).

    Raises:
        TailscaleError: If Tailscale is not ready or Funnel cannot start.
    """
    base = (serve_dir or DEFAULT_SERVE_DIR).expanduser()
    well_known_dir = base / ".well-known"
    if not well_known_dir.exists():
        raise TailscaleError(
            f"Serve directory not found: {well_known_dir}. "
            "Run deploy_public_key_tailscale() first."
        )

    ts = TailscaleManager()
    await ts.check_available()
    hostname = await ts.get_hostname()

    # Serve the .well-known directory at /.well-known/
    await ts.start_serve("/.well-known/", str(well_known_dir))

    # Enable Funnel to make it publicly accessible
    await ts.enable_funnel()

    logger.info("Key serving started at https://%s/%s", hostname, WELL_KNOWN_PATH)
    return hostname


async def stop_key_serving() -> None:
    """Remove the ``.well-known`` serve handler."""
    ts = TailscaleManager()
    await ts.stop_serve("/.well-known/")
    logger.info("Key serving stopped")


# ---------------------------------------------------------------------------
# Readiness check
# ---------------------------------------------------------------------------


async def is_tailscale_serve_ready() -> bool:
    """Quick check: CLI on PATH + daemon running + Funnel available.

    Returns bool, never raises.
    """
    try:
        ts = TailscaleManager()
        await ts.check_available()
        await ts.check_running()
        return await ts.check_funnel_available()
    except (TailscaleError, Exception):
        return False


# ---------------------------------------------------------------------------
# URL helpers and validation
# ---------------------------------------------------------------------------


def get_key_url(hostname: str) -> str:
    """Return full URL to the public key."""
    return f"https://{hostname}/{WELL_KNOWN_PATH}"


async def validate_tailscale_key_url(hostname: str) -> bool:
    """HTTP GET to verify key is accessible.

    Returns True if the key is reachable and contains PEM content.
    """
    url = get_key_url(hostname)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True, timeout=10)
            return resp.status_code == 200 and "BEGIN PUBLIC KEY" in resp.text
    except httpx.HTTPError:
        return False


async def wait_for_tailscale_deployment(
    hostname: str,
    *,
    timeout: int = DEFAULT_DEPLOY_TIMEOUT,
) -> bool:
    """Poll key URL until accessible or *timeout* elapses.

    Returns True if the key became accessible, False on timeout.
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if await validate_tailscale_key_url(hostname):
            return True
        await asyncio.sleep(POLL_INTERVAL)

    return False
