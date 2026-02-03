"""Tailscale Funnel deployment helpers for Tesla Fleet API public keys.

Serves the public key at the Tesla-required ``.well-known`` path via
Tailscale's ``serve`` + ``funnel`` commands.  All Tailscale interaction
goes through :class:`~tescmd.telemetry.tailscale.TailscaleManager`.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
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
# In-process key server (used by interactive setup)
# ---------------------------------------------------------------------------


class _KeyRequestHandler(BaseHTTPRequestHandler):
    """Serve the root (200 OK) and the ``.well-known`` PEM path."""

    server: KeyServer

    def do_GET(self) -> None:
        if self.path == "/":
            self._respond(200, "")
        elif self.path == f"/{WELL_KNOWN_PATH}":
            self._respond(
                200,
                self.server.pem_content,
                content_type="application/x-pem-file",
            )
        else:
            self._respond(404, "Not found")

    def _respond(
        self,
        status: int,
        body: str,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        """Silence default stderr logging."""


class KeyServer(HTTPServer):
    """Ephemeral HTTP server that serves a PEM public key.

    Runs in a daemon thread so the main process can continue interacting
    with the user.  Tailscale Funnel proxies external HTTPS traffic to
    this local server.
    """

    def __init__(self, pem_content: str, port: int) -> None:
        super().__init__(("127.0.0.1", port), _KeyRequestHandler)
        self.pem_content = pem_content
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start serving in a background daemon thread."""
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Shut down the server and wait for the thread to exit."""
        self.shutdown()
        self.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


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
    """Start ``tailscale serve`` with Funnel for ``.well-known``.

    Uses a single ``tailscale serve --bg --funnel --set-path / <dir>``
    command so that the static-file handler and public Funnel access are
    configured atomically on HTTPS port 443.

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

    # Serve the entire base directory at / with Funnel enabled so that:
    #   - The origin URL (https://host/) returns 200
    #   - The key at /.well-known/appspecific/com.tesla.3p.public-key.pem is reachable
    # Tesla verifies both during Developer Portal app configuration.
    await ts.start_serve("/", str(base), funnel=True)

    logger.info("Key serving started at https://%s/%s", hostname, WELL_KNOWN_PATH)
    return hostname


async def stop_key_serving() -> None:
    """Remove the key-serving handler."""
    ts = TailscaleManager()
    await ts.stop_serve("/")
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


def fetch_tailscale_key_pem(hostname: str) -> str | None:
    """Fetch the public key PEM from a Tailscale Funnel ``.well-known`` URL.

    Returns the PEM string (stripped), or ``None`` if the key is not
    accessible or does not look like a PEM public key.
    """
    url = get_key_url(hostname)
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=10)
        if resp.status_code == 200 and "BEGIN PUBLIC KEY" in resp.text:
            return resp.text.strip()
    except httpx.HTTPError:
        pass
    return None


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
