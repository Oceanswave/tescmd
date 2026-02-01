"""Reusable telemetry session lifecycle.

Encapsulates the full setup and teardown sequence shared by the telemetry
stream command and the OpenClaw bridge:

    server start → tunnel → partner re-registration → fleet config → yield → cleanup

Usage::

    async with telemetry_session(app_ctx, vin, ...) as session:
        # session.server is running, fleet config is active
        await some_blocking_loop()
    # cleanup is guaranteed (config delete → domain restore → funnel stop → server stop)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tescmd.api.errors import TunnelError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from tescmd.cli.main import AppContext
    from tescmd.output.formatter import OutputFormatter
    from tescmd.telemetry.decoder import TelemetryFrame
    from tescmd.telemetry.server import TelemetryServer

logger = logging.getLogger(__name__)


@dataclass
class TelemetrySession:
    """Active telemetry session state exposed to callers."""

    server: TelemetryServer
    tunnel_url: str
    hostname: str
    vin: str
    port: int


async def _noop_stop() -> None:
    """No-op tunnel cleanup (used when tunnel wasn't started yet)."""


async def _setup_tunnel(
    *,
    port: int,
    formatter: OutputFormatter,
) -> tuple[str, str, str, Callable[[], Awaitable[None]]]:
    """Start Tailscale Funnel and return ``(url, hostname, ca_pem, stop_fn)``."""
    from tescmd.telemetry.tailscale import TailscaleManager

    ts = TailscaleManager()
    await ts.check_available()
    await ts.check_running()

    url = await ts.start_funnel(port)
    if formatter.format != "json":
        formatter.rich.info(f"Tailscale Funnel active: {url}")

    hostname = await ts.get_hostname()
    ca_pem = await ts.get_cert_pem()
    return url, hostname, ca_pem, ts.stop_funnel


async def _register_partner_domain(
    *,
    hostname: str,
    settings: Any,
    app_ctx: AppContext,
    formatter: OutputFormatter,
    interactive: bool,
) -> str | None:
    """Re-register partner domain if tunnel hostname differs from registered.

    Returns the original partner domain if it was changed (for restore on
    cleanup), or ``None`` if no change was needed.
    """
    from tescmd.api.errors import AuthError
    from tescmd.auth.oauth import register_partner_account

    registered_domain = (settings.domain or "").lower().rstrip(".")
    tunnel_host = hostname.lower().rstrip(".")

    if tunnel_host == registered_domain:
        return None

    if not settings.client_id or not settings.client_secret:
        raise TunnelError(
            "Client credentials required for partner domain "
            "re-registration. Ensure TESLA_CLIENT_ID and "
            "TESLA_CLIENT_SECRET are set."
        )

    reg_client_id = settings.client_id
    reg_client_secret = settings.client_secret
    region = app_ctx.region or settings.region
    if formatter.format != "json":
        formatter.rich.info(f"Re-registering partner domain: {hostname}")

    async def _try_register() -> None:
        await register_partner_account(
            client_id=reg_client_id,
            client_secret=reg_client_secret,
            domain=hostname,
            region=region,
        )

    max_retries = 12
    for attempt in range(max_retries):
        try:
            await _try_register()
            if attempt > 0 and formatter.format != "json":
                formatter.rich.info("[green]Tunnel is reachable — registration succeeded.[/green]")
            break
        except AuthError as exc:
            status = getattr(exc, "status_code", None)

            # 424 = key download failed — likely tunnel propagation delay
            if status == 424 and attempt < max_retries - 1:
                if formatter.format != "json":
                    formatter.rich.info(
                        f"[yellow]Waiting for tunnel to become reachable "
                        f"(HTTP 424)... "
                        f"({attempt + 1}/{max_retries})[/yellow]"
                    )
                await asyncio.sleep(5)
                continue

            if status not in (412, 424):
                raise TunnelError(f"Partner re-registration failed for {hostname}: {exc}") from exc

            # 412 or exhausted 424 retries — need user intervention
            if not interactive or formatter.format == "json":
                if status == 412:
                    raise TunnelError(
                        f"Add https://{hostname} as an Allowed Origin "
                        f"URL in your Tesla Developer Portal app, "
                        f"then try again."
                    ) from exc
                raise TunnelError(
                    f"Tesla could not fetch the public key from "
                    f"https://{hostname}. Verify the tunnel is "
                    f"accessible and try again."
                ) from exc

            formatter.rich.info("")
            if status == 412:
                formatter.rich.info(
                    "[yellow]Tesla requires the tunnel domain as an Allowed Origin URL.[/yellow]"
                )
            else:
                formatter.rich.info(
                    "[yellow]Tesla could not reach the tunnel to "
                    "verify the public key (HTTP 424).[/yellow]"
                )
            formatter.rich.info("")
            formatter.rich.info("  1. Open your Tesla Developer app:")
            formatter.rich.info("     [cyan]https://developer.tesla.com[/cyan]")
            formatter.rich.info("  2. Add this as an Allowed Origin URL:")
            formatter.rich.info(f"     [cyan]https://{hostname}[/cyan]")
            formatter.rich.info("  3. Save the changes")
            formatter.rich.info("")

            # Wait for user to fix, then retry
            while True:
                formatter.rich.info("Press [bold]Enter[/bold] when done (or Ctrl+C to cancel)...")
                await asyncio.get_event_loop().run_in_executor(None, input)
                try:
                    await _try_register()
                    formatter.rich.info("[green]Registration succeeded![/green]")
                    break
                except AuthError as retry_exc:
                    retry_status = getattr(retry_exc, "status_code", None)
                    if retry_status in (412, 424):
                        formatter.rich.info(
                            f"[yellow]Tesla returned HTTP "
                            f"{retry_status}. There is a propagation "
                            f"delay on Tesla's end after adding an "
                            f"Allowed Origin URL — this can take up "
                            f"to 5 minutes.[/yellow]"
                        )
                        formatter.rich.info(
                            "Press [bold]Enter[/bold] to retry, or "
                            "wait and try again (Ctrl+C to cancel)..."
                        )
                        continue
                    raise TunnelError(
                        f"Partner re-registration failed: {retry_exc}"
                    ) from retry_exc
            break  # registration succeeded in the inner loop

    domain: str | None = settings.domain
    return domain


async def _create_fleet_config(
    *,
    api: Any,
    client: Any,
    vin: str,
    hostname: str,
    ca_pem: str,
    field_config: dict[str, Any],
    key_dir: Path,
    settings: Any,
    app_ctx: AppContext,
    formatter: OutputFormatter,
    interactive: bool,
) -> None:
    """Sign and create the fleet telemetry configuration."""
    from tescmd.api.errors import MissingScopesError
    from tescmd.crypto.keys import load_private_key
    from tescmd.crypto.schnorr import sign_fleet_telemetry_config

    inner_config: dict[str, object] = {
        "hostname": hostname,
        "port": 443,  # Tailscale Funnel terminates TLS on 443
        "ca": ca_pem,
        "fields": field_config,
        "alert_types": ["service"],
    }

    private_key = load_private_key(key_dir)
    jws_token = sign_fleet_telemetry_config(private_key, inner_config)

    try:
        await api.fleet_telemetry_config_create_jws(vins=[vin], token=jws_token)
    except MissingScopesError:
        if not interactive or formatter.format == "json":
            raise TunnelError(
                "Your OAuth token is missing required scopes for "
                "telemetry streaming. Run:\n"
                "  1. tescmd auth register   (restore partner domain)\n"
                "  2. tescmd auth login       (obtain token with updated scopes)\n"
                "Then retry the stream command."
            ) from None

        from tescmd.auth.oauth import login_flow
        from tescmd.auth.token_store import TokenStore
        from tescmd.models.auth import DEFAULT_SCOPES

        formatter.rich.info("")
        formatter.rich.info(
            "[yellow]Token is missing required scopes — re-authenticating...[/yellow]"
        )
        formatter.rich.info("Opening your browser to sign in to Tesla...")
        formatter.rich.info(
            "When prompted, click [cyan]Select All[/cyan] and then"
            " [cyan]Allow[/cyan] to grant tescmd access."
        )

        login_port = 8085
        login_redirect = f"http://localhost:{login_port}/callback"
        login_store = TokenStore(
            profile=app_ctx.profile,
            token_file=settings.token_file,
            config_dir=settings.config_dir,
        )
        token_data = await login_flow(
            client_id=settings.client_id or "",
            client_secret=settings.client_secret,
            redirect_uri=login_redirect,
            scopes=DEFAULT_SCOPES,
            port=login_port,
            token_store=login_store,
            region=app_ctx.region or settings.region,
        )
        client.update_token(token_data.access_token)
        formatter.rich.info("[green]Login successful — retrying config...[/green]")
        await api.fleet_telemetry_config_create_jws(vins=[vin], token=jws_token)


@asynccontextmanager
async def telemetry_session(
    app_ctx: AppContext,
    vin: str,
    port: int,
    field_config: dict[str, Any],
    on_frame: Callable[[TelemetryFrame], Awaitable[None]],
    *,
    interactive: bool = True,
) -> AsyncIterator[TelemetrySession]:
    """Shared lifecycle for telemetry consumers.

    Manages: server start → tunnel → partner registration → fleet config
    → yield ``TelemetrySession`` → cleanup (config delete → domain restore
    → funnel stop → server stop → client close).

    Parameters
    ----------
    app_ctx:
        CLI application context.
    vin:
        Vehicle VIN to stream telemetry from.
    port:
        Local WebSocket server port.
    field_config:
        Resolved field configuration mapping field IDs to intervals.
    on_frame:
        Async callback invoked for each decoded telemetry frame.
    interactive:
        If ``False``, skip interactive prompts (headless bridge mode).
        Errors that would normally prompt user input are raised instead.
    """
    from tescmd.crypto.keys import load_public_key_pem
    from tescmd.models.config import AppSettings
    from tescmd.telemetry.decoder import TelemetryDecoder
    from tescmd.telemetry.server import TelemetryServer

    formatter = app_ctx.formatter

    _settings = AppSettings()
    key_dir = Path(_settings.config_dir).expanduser() / "keys"
    public_key_pem = load_public_key_pem(key_dir)

    # Build API client
    from tescmd.cli._client import get_vehicle_api

    client, api = get_vehicle_api(app_ctx)
    decoder = TelemetryDecoder()

    server = TelemetryServer(
        port=port, decoder=decoder, on_frame=on_frame, public_key_pem=public_key_pem
    )

    config_created = False
    stop_tunnel: Callable[[], Awaitable[None]] = _noop_stop
    original_partner_domain: str | None = None
    tunnel_url = ""
    hostname = ""

    try:
        await server.start()

        if formatter.format != "json":
            formatter.rich.info(f"WebSocket server listening on port {port}")

        tunnel_url, hostname, ca_pem, stop_tunnel = await _setup_tunnel(
            port=port,
            formatter=formatter,
        )

        # Re-register partner domain if tunnel hostname differs
        original_partner_domain = await _register_partner_domain(
            hostname=hostname,
            settings=_settings,
            app_ctx=app_ctx,
            formatter=formatter,
            interactive=interactive,
        )

        # Create fleet telemetry config
        await _create_fleet_config(
            api=api,
            client=client,
            vin=vin,
            hostname=hostname,
            ca_pem=ca_pem,
            field_config=field_config,
            key_dir=key_dir,
            settings=_settings,
            app_ctx=app_ctx,
            formatter=formatter,
            interactive=interactive,
        )
        config_created = True

        if formatter.format != "json":
            formatter.rich.info(f"Fleet telemetry configured for VIN {vin}")
            formatter.rich.info("")

        yield TelemetrySession(
            server=server,
            tunnel_url=tunnel_url,
            hostname=hostname,
            vin=vin,
            port=port,
        )

    finally:
        # Cleanup in reverse order — each tolerates failure.
        # Suppress noisy library loggers so shutdown messages stay clean.
        for _logger_name in ("httpx", "httpcore", "websockets", "mcp"):
            logging.getLogger(_logger_name).setLevel(logging.WARNING)

        is_rich = formatter.format != "json"

        if config_created:
            if is_rich:
                formatter.rich.info("[dim]Removing fleet telemetry config...[/dim]")
            try:
                await api.fleet_telemetry_config_delete(vin)
            except Exception:
                if is_rich:
                    formatter.rich.info(
                        "[yellow]Warning: failed to remove telemetry config."
                        " It may expire or can be removed manually.[/yellow]"
                    )

        if original_partner_domain is not None:
            if is_rich:
                formatter.rich.info(
                    f"[dim]Restoring partner domain to {original_partner_domain}...[/dim]"
                )
            try:
                from tescmd.auth.oauth import register_partner_account

                assert _settings.client_id is not None
                assert _settings.client_secret is not None
                await register_partner_account(
                    client_id=_settings.client_id,
                    client_secret=_settings.client_secret,
                    domain=original_partner_domain,
                    region=app_ctx.region or _settings.region,
                )
            except Exception:
                msg = (
                    f"Failed to restore partner domain to {original_partner_domain}. "
                    "Run 'tescmd auth register' to fix this manually."
                )
                logger.warning(msg)
                if is_rich:
                    formatter.rich.info(f"[yellow]Warning: {msg}[/yellow]")

        if is_rich:
            formatter.rich.info("[dim]Stopping tunnel...[/dim]")
        import contextlib

        with contextlib.suppress(Exception):
            await stop_tunnel()

        if is_rich:
            formatter.rich.info("[dim]Stopping server...[/dim]")
        with contextlib.suppress(Exception):
            await server.stop()

        await client.close()
        if is_rich:
            formatter.rich.info("[green]Stream stopped.[/green]")
