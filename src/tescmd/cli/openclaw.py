"""CLI commands for OpenClaw integration."""

from __future__ import annotations

import asyncio
import logging
import random

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import require_vin
from tescmd.cli._options import global_options

logger = logging.getLogger(__name__)

openclaw_group = click.Group("openclaw", help="OpenClaw integration commands.")


@openclaw_group.command("bridge")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--gateway", default=None, help="Gateway WebSocket URL (default: ws://127.0.0.1:18789)"
)
@click.option(
    "--token",
    default=None,
    envvar="OPENCLAW_GATEWAY_TOKEN",
    help="Gateway auth token (env: OPENCLAW_GATEWAY_TOKEN)",
)
@click.option("--config", "config_path", default=None, help="Bridge config JSON path")
@click.option(
    "--port", type=int, default=None, help="Local telemetry server port (random if omitted)"
)
@click.option("--fields", default="default", help="Field preset or comma-separated names")
@click.option(
    "--interval", type=int, default=None, help="Override telemetry interval for all fields"
)
@click.option("--dry-run", is_flag=True, default=False, help="Log events as JSONL without sending")
@global_options
def bridge_cmd(
    app_ctx: object,
    vin_positional: str | None,
    gateway: str | None,
    token: str | None,
    config_path: str | None,
    port: int | None,
    fields: str,
    interval: int | None,
    dry_run: bool,
) -> None:
    """Stream Fleet Telemetry to an OpenClaw Gateway.

    Starts a local WebSocket server, exposes it via Tailscale Funnel,
    configures the vehicle to push telemetry, and bridges events to
    an OpenClaw Gateway with delta+throttle filtering.

    Requires Tailscale with Funnel enabled.

    \b
    Examples:
      tescmd openclaw bridge 5YJ3...         # default gateway (localhost:18789)
      tescmd openclaw bridge --dry-run       # log events without sending
      tescmd openclaw bridge --gateway ws://gw.example.com:18789
    """
    from tescmd.cli.main import AppContext

    assert isinstance(app_ctx, AppContext)
    run_async(
        _cmd_bridge(
            app_ctx,
            vin_positional,
            gateway,
            token,
            config_path,
            port,
            fields,
            interval,
            dry_run,
        )
    )


async def _cmd_bridge(
    app_ctx: object,
    vin_positional: str | None,
    gateway_url: str | None,
    gateway_token: str | None,
    config_path: str | None,
    port: int | None,
    fields_spec: str,
    interval_override: int | None,
    dry_run: bool,
) -> None:
    from tescmd.cli.main import AppContext
    from tescmd.openclaw.bridge import TelemetryBridge
    from tescmd.openclaw.config import BridgeConfig
    from tescmd.openclaw.emitter import EventEmitter
    from tescmd.openclaw.filters import DualGateFilter
    from tescmd.openclaw.gateway import GatewayClient
    from tescmd.telemetry.fields import resolve_fields
    from tescmd.telemetry.setup import telemetry_session

    assert isinstance(app_ctx, AppContext)
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)

    if port is None:
        port = random.randint(49152, 65534)

    field_config = resolve_fields(fields_spec, interval_override)

    # Load bridge config
    config = BridgeConfig.load(config_path)
    config = config.merge_overrides(
        gateway_url=gateway_url,
        gateway_token=gateway_token,
    )

    # Build pipeline components
    filt = DualGateFilter(config.telemetry)
    emitter = EventEmitter(client_id=config.client_id)
    gw = GatewayClient(
        config.gateway_url,
        token=config.gateway_token,
        client_id=config.client_id,
        client_version=config.client_version,
    )
    bridge = TelemetryBridge(gw, filt, emitter, dry_run=dry_run)

    # Build fanout with the OpenClaw bridge as the primary sink
    from tescmd.telemetry.fanout import FrameFanout

    fanout = FrameFanout()
    fanout.add_sink(bridge.on_frame)

    # Connect to gateway (unless dry-run)
    if not dry_run:
        if formatter.format != "json":
            formatter.rich.info(f"Connecting to OpenClaw Gateway: {config.gateway_url}")
        await gw.connect_with_backoff(max_attempts=5)
        if formatter.format != "json":
            formatter.rich.info("[green]Connected to gateway.[/green]")
    else:
        if formatter.format != "json":
            formatter.rich.info("[yellow]Dry-run mode — events will be logged as JSONL.[/yellow]")

    try:
        async with telemetry_session(
            app_ctx, vin, port, field_config, fanout.on_frame, interactive=False
        ):
            if formatter.format != "json":
                formatter.rich.info(f"Bridge running: telemetry → {config.gateway_url}")

            if formatter.format != "json":
                formatter.rich.info("Press Ctrl+C to stop.")
                formatter.rich.info("")

            await _wait_for_interrupt()

            if formatter.format != "json":
                formatter.rich.info(
                    f"\n[dim]Events sent: {bridge.event_count}, dropped: {bridge.drop_count}[/dim]"
                )
    finally:
        await gw.close()


async def _wait_for_interrupt() -> None:
    """Block until Ctrl+C."""
    try:
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
