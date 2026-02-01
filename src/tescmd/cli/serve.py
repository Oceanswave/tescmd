"""Unified ``tescmd serve`` command — MCP + telemetry cache warming + optional OpenClaw."""

from __future__ import annotations

import logging
import random

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import require_vin
from tescmd.cli._options import global_options

logger = logging.getLogger(__name__)


@click.command("serve")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "streamable-http"]),
    default="streamable-http",
    help="MCP transport (default: streamable-http)",
)
@click.option("--port", type=int, default=8080, help="MCP HTTP port (streamable-http only)")
@click.option(
    "--telemetry-port",
    type=int,
    default=None,
    help="WebSocket port for telemetry (random if omitted)",
)
@click.option(
    "--fields",
    default="default",
    help="Telemetry field preset or comma-separated names",
)
@click.option(
    "--interval",
    type=int,
    default=None,
    help="Override telemetry interval for all fields",
)
@click.option(
    "--no-telemetry",
    is_flag=True,
    default=False,
    help="MCP-only mode — skip telemetry and cache warming",
)
@click.option(
    "--no-mcp",
    is_flag=True,
    default=False,
    help="Telemetry-only mode — skip MCP server",
)
@click.option(
    "--no-log",
    is_flag=True,
    default=False,
    help="Disable CSV telemetry log (enabled by default when telemetry active)",
)
@click.option(
    "--legacy-dashboard",
    is_flag=True,
    default=False,
    help="Use the legacy Rich Live dashboard instead of the full-screen TUI",
)
@click.option(
    "--openclaw",
    "openclaw_url",
    default=None,
    help="Also bridge to an OpenClaw gateway (ws://...)",
)
@click.option(
    "--openclaw-token",
    default=None,
    envvar="OPENCLAW_GATEWAY_TOKEN",
    help="OpenClaw gateway auth token (env: OPENCLAW_GATEWAY_TOKEN)",
)
@click.option(
    "--openclaw-config",
    "openclaw_config_path",
    type=click.Path(exists=True),
    default=None,
    help="OpenClaw bridge config file (JSON)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="OpenClaw dry-run: log events as JSONL instead of sending",
)
@click.option("--tailscale", is_flag=True, default=False, help="Expose MCP via Tailscale Funnel")
@click.option(
    "--client-id",
    envvar="TESCMD_MCP_CLIENT_ID",
    default=None,
    help="MCP client ID (env: TESCMD_MCP_CLIENT_ID)",
)
@click.option(
    "--client-secret",
    envvar="TESCMD_MCP_CLIENT_SECRET",
    default=None,
    help="MCP client secret / bearer token (env: TESCMD_MCP_CLIENT_SECRET)",
)
@global_options
def serve_cmd(
    app_ctx: object,
    vin_positional: str | None,
    transport: str,
    port: int,
    telemetry_port: int | None,
    fields: str,
    interval: int | None,
    no_telemetry: bool,
    no_mcp: bool,
    no_log: bool,
    legacy_dashboard: bool,
    openclaw_url: str | None,
    openclaw_token: str | None,
    openclaw_config_path: str | None,
    dry_run: bool,
    tailscale: bool,
    client_id: str | None,
    client_secret: str | None,
) -> None:
    """Start a unified MCP + telemetry server.

    Combines the MCP server with telemetry-driven cache warming so that
    agent reads are free while telemetry is active.  Optionally bridges
    to an OpenClaw gateway.

    When telemetry is active on a TTY, a full-screen dashboard shows live
    data, server info, and operational metadata.  A wide-format CSV log
    is written by default (disable with --no-log).

    \b
    Modes:
      Default           MCP + telemetry cache warming + TUI dashboard
      --no-telemetry    MCP-only (same as 'tescmd mcp serve')
      --no-mcp          Telemetry-only (dashboard or JSONL)
      --openclaw URL    Also bridge telemetry to OpenClaw

    \b
    Examples:
      tescmd serve 5YJ3...                              # MCP + cache warming
      tescmd serve --no-telemetry                       # MCP only
      tescmd serve 5YJ3... --no-mcp                     # Telemetry dashboard only
      tescmd serve --openclaw ws://gw.example.com:18789 # MCP + cache + OpenClaw
      tescmd serve --transport stdio                    # stdio for Claude Desktop
      tescmd serve --legacy-dashboard                   # Use Rich Live dashboard
    """
    from tescmd.cli.main import AppContext

    assert isinstance(app_ctx, AppContext)

    # -- Validation --
    if no_mcp and no_telemetry:
        raise click.UsageError("--no-mcp and --no-telemetry cannot both be set (nothing to run).")

    if no_mcp and transport == "stdio":
        raise click.UsageError(
            "--no-mcp cannot be used with --transport stdio (stdio is MCP-only)."
        )

    if not no_mcp and (not client_id or not client_secret):
        raise click.UsageError(
            "MCP client credentials required.\n"
            "Set TESCMD_MCP_CLIENT_ID and TESCMD_MCP_CLIENT_SECRET "
            "in your .env file or environment, or pass --client-id and --client-secret.\n"
            "Use --no-mcp to run in telemetry-only mode without credentials."
        )

    if tailscale and transport == "stdio":
        raise click.UsageError("--tailscale cannot be used with --transport stdio")

    if openclaw_url and no_telemetry:
        raise click.UsageError("--openclaw requires telemetry. Remove --no-telemetry.")

    if dry_run and not openclaw_url:
        raise click.UsageError("--dry-run requires --openclaw.")

    if openclaw_config_path and not openclaw_url:
        raise click.UsageError("--openclaw-config requires --openclaw.")

    run_async(
        _cmd_serve(
            app_ctx,
            vin_positional=vin_positional,
            transport=transport,
            mcp_port=port,
            telemetry_port=telemetry_port,
            fields_spec=fields,
            interval_override=interval,
            no_telemetry=no_telemetry,
            no_mcp=no_mcp,
            no_log=no_log,
            legacy_dashboard=legacy_dashboard,
            openclaw_url=openclaw_url,
            openclaw_token=openclaw_token,
            openclaw_config_path=openclaw_config_path,
            dry_run=dry_run,
            tailscale=tailscale,
            client_id=client_id or "",
            client_secret=client_secret or "",
        )
    )


async def _cmd_serve(
    app_ctx: object,
    *,
    vin_positional: str | None,
    transport: str,
    mcp_port: int,
    telemetry_port: int | None,
    fields_spec: str,
    interval_override: int | None,
    no_telemetry: bool,
    no_mcp: bool,
    no_log: bool,
    legacy_dashboard: bool,
    openclaw_url: str | None,
    openclaw_token: str | None,
    openclaw_config_path: str | None,
    dry_run: bool,
    tailscale: bool,
    client_id: str,
    client_secret: str,
) -> None:
    import asyncio
    import contextlib
    import json
    import sys

    from tescmd.cli.main import AppContext
    from tescmd.telemetry.fanout import FrameFanout

    assert isinstance(app_ctx, AppContext)
    formatter = app_ctx.formatter

    is_tty = sys.stdin.isatty() and transport != "stdio"
    interactive = is_tty

    # -- MCP server setup (unless --no-mcp) --
    mcp_server = None
    tool_count = 0
    if not no_mcp:
        from tescmd.mcp.server import create_mcp_server

        mcp_server = create_mcp_server(client_id=client_id, client_secret=client_secret)
        tool_count = len(mcp_server.list_tools())

    # -- stdio mode: no telemetry, no fanout --
    if transport == "stdio" and mcp_server is not None:
        print(f"tescmd serve starting (stdio, {tool_count} tools)", file=sys.stderr)
        await mcp_server.run_stdio()
        return

    # -- Build telemetry fanout --
    fanout = FrameFanout()
    cache_sink = None
    csv_sink = None
    gw = None
    dashboard = None
    tui = None
    vin: str | None = None
    field_config: dict[str, dict[str, int]] | None = None

    if not no_telemetry:
        from tescmd.cli._client import get_cache
        from tescmd.telemetry.cache_sink import CacheSink
        from tescmd.telemetry.fields import resolve_fields
        from tescmd.telemetry.mapper import TelemetryMapper

        vin = require_vin(vin_positional, app_ctx.vin)

        if telemetry_port is None:
            telemetry_port = random.randint(49152, 65534)

        field_config = resolve_fields(fields_spec, interval_override)

        # Cache sink — warms the response cache from telemetry
        cache = get_cache(app_ctx)
        mapper = TelemetryMapper()
        cache_sink = CacheSink(cache, mapper, vin)
        fanout.add_sink(cache_sink.on_frame)

        if formatter.format != "json":
            formatter.rich.info(f"Cache warming enabled for {vin}")

        # CSV log sink — wide-format telemetry log (default on)
        if not no_log:
            from tescmd.telemetry.csv_sink import CSVLogSink, create_log_path

            csv_path = create_log_path(vin)
            csv_sink = CSVLogSink(csv_path, vin=vin)
            fanout.add_sink(csv_sink.on_frame)

            if formatter.format != "json":
                formatter.rich.info(f"CSV log: {csv_path}")

        # Display sink: TUI (default) / legacy Rich.Live dashboard / JSONL
        if interactive and formatter.format != "json":
            if legacy_dashboard:
                # Legacy Rich Live dashboard (fallback)
                from tescmd.telemetry.dashboard import TelemetryDashboard

                dashboard = TelemetryDashboard(formatter.console, formatter.rich._units)

                async def _dashboard_on_frame(frame: object) -> None:
                    from tescmd.telemetry.decoder import TelemetryFrame

                    assert isinstance(frame, TelemetryFrame)
                    assert dashboard is not None
                    dashboard.update(frame)

                fanout.add_sink(_dashboard_on_frame)
            else:
                # Full-screen Textual TUI (new default)
                from tescmd.telemetry.tui import TelemetryTUI

                tui = TelemetryTUI(
                    formatter.rich._units,
                    vin=vin,
                    telemetry_port=telemetry_port,
                )
                fanout.add_sink(tui.push_frame)
        elif no_mcp:
            # JSONL output when in telemetry-only piped mode
            async def _jsonl_sink(frame: object) -> None:
                from tescmd.telemetry.decoder import TelemetryFrame

                assert isinstance(frame, TelemetryFrame)
                line = json.dumps(
                    {
                        "vin": frame.vin,
                        "timestamp": frame.created_at.isoformat(),
                        "data": {d.field_name: d.value for d in frame.data},
                    },
                    default=str,
                )
                print(line, flush=True)

            fanout.add_sink(_jsonl_sink)

        # OpenClaw sink — optional bridge to an OpenClaw gateway
        if openclaw_url:
            from pathlib import Path

            from tescmd.openclaw.bridge import TelemetryBridge
            from tescmd.openclaw.config import BridgeConfig
            from tescmd.openclaw.emitter import EventEmitter
            from tescmd.openclaw.filters import DualGateFilter
            from tescmd.openclaw.gateway import GatewayClient

            if openclaw_config_path:
                config = BridgeConfig.load(Path(openclaw_config_path))
            else:
                config = BridgeConfig.load()
            config = config.merge_overrides(
                gateway_url=openclaw_url,
                gateway_token=openclaw_token,
            )
            filt = DualGateFilter(config.telemetry)
            emitter = EventEmitter(client_id=config.client_id)
            gw = GatewayClient(
                config.gateway_url,
                token=config.gateway_token,
                client_id=config.client_id,
                client_version=config.client_version,
            )
            bridge = TelemetryBridge(gw, filt, emitter, dry_run=dry_run)
            fanout.add_sink(bridge.on_frame)

            if not dry_run:
                if formatter.format != "json":
                    formatter.rich.info(f"Connecting to OpenClaw Gateway: {config.gateway_url}")
                await gw.connect_with_backoff(max_attempts=5)
                if formatter.format != "json":
                    formatter.rich.info("[green]Connected to OpenClaw gateway.[/green]")
            else:
                if formatter.format != "json":
                    formatter.rich.info(
                        "[yellow]Dry-run mode — events will be logged as JSONL to stderr.[/yellow]"
                    )

    # -- Tailscale Funnel setup (optional) --
    public_url: str | None = None
    ts = None
    if tailscale:
        from tescmd.telemetry.tailscale import TailscaleManager

        ts = TailscaleManager()
        await ts.check_available()
        await ts.check_running()
        funnel_url = await ts.start_funnel(mcp_port)
        public_url = funnel_url

        if formatter.format != "json":
            formatter.rich.info(f"Tailscale Funnel active: {funnel_url}/mcp")
        else:
            print(f'{{"url": "{funnel_url}/mcp"}}', file=sys.stderr)

    # -- Populate TUI with server info --
    if tui is not None:
        mcp_url = ""
        if not no_mcp:
            mcp_url = f"{public_url}/mcp" if public_url else f"http://127.0.0.1:{mcp_port}/mcp"
            tui.set_mcp_url(mcp_url)
        if public_url:
            tui.set_tunnel_url(public_url)
        tui.set_sink_count(fanout.sink_count)
        if csv_sink is not None:
            tui.set_log_path(csv_sink.log_path)

    # -- Start everything --
    if not no_mcp and formatter.format != "json" and tui is None:
        base_url = f"{public_url}/mcp" if public_url else f"http://127.0.0.1:{mcp_port}/mcp"
        formatter.rich.info(
            f"MCP server starting on {base_url} ({tool_count} tools, "
            f"{fanout.sink_count} telemetry sink(s))"
        )
    if (not no_mcp or not no_telemetry) and formatter.format != "json" and tui is None:
        formatter.rich.info("Press Ctrl+C to stop.")

    try:
        if fanout.has_sinks() and vin is not None and field_config is not None:
            from tescmd.telemetry.setup import telemetry_session

            assert telemetry_port is not None
            async with telemetry_session(
                app_ctx,
                vin,
                telemetry_port,
                field_config,
                fanout.on_frame,
                interactive=interactive,
            ) as session:
                if tui is not None:
                    tui.set_tunnel_url(session.tunnel_url)

                if formatter.format != "json" and tui is None:
                    formatter.rich.info("Telemetry pipeline active.")

                if tui is not None:
                    # Run TUI as the main display + MCP concurrently.
                    if no_mcp:
                        await tui.run_async()
                    else:
                        assert mcp_server is not None
                        tui_task = asyncio.create_task(tui.run_async())
                        mcp_task = asyncio.create_task(
                            mcp_server.run_http(port=mcp_port, public_url=public_url)
                        )
                        # Wait for TUI shutdown signal (user pressed q).
                        await tui.shutdown_event.wait()
                        # Cancel both tasks to trigger cleanup.
                        for task in (tui_task, mcp_task):
                            if not task.done():
                                task.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await task
                elif dashboard is not None:
                    from rich.live import Live

                    dashboard.set_tunnel_url(session.tunnel_url)
                    with Live(
                        dashboard,
                        console=formatter.console,
                        refresh_per_second=4,
                    ) as live:
                        dashboard.set_live(live)
                        if no_mcp:
                            await _wait_for_interrupt()
                        else:
                            assert mcp_server is not None
                            await mcp_server.run_http(port=mcp_port, public_url=public_url)
                elif no_mcp:
                    await _wait_for_interrupt()
                else:
                    assert mcp_server is not None
                    await mcp_server.run_http(port=mcp_port, public_url=public_url)
        elif mcp_server is not None:
            await mcp_server.run_http(port=mcp_port, public_url=public_url)
    finally:
        if ts is not None:
            await ts.stop_funnel()
            if formatter.format != "json":
                formatter.rich.info("Tailscale Funnel stopped.")
        if gw is not None:
            await gw.close()
        if csv_sink is not None:
            csv_sink.close()
            if formatter.format != "json":
                formatter.rich.info(
                    f"[dim]CSV log: {csv_sink.log_path} ({csv_sink.frame_count} frames)[/dim]"
                )
            else:
                print(
                    f'{{"csv_log": "{csv_sink.log_path}", "frames": {csv_sink.frame_count}}}',
                    file=sys.stderr,
                )
        if tui is not None:
            cmd_log = getattr(tui, "_cmd_log_path", "")
            if cmd_log and formatter.format != "json":
                formatter.rich.info(f"[dim]Command log: {cmd_log}[/dim]")
        if cache_sink is not None:
            cache_sink.flush()
            if formatter.format != "json":
                formatter.rich.info(
                    f"[dim]Cache sink: {cache_sink.frame_count} frames, "
                    f"{cache_sink.field_count} field updates[/dim]"
                )


async def _wait_for_interrupt() -> None:
    """Block until Ctrl+C or 'q' is pressed."""
    import asyncio
    import sys

    if not sys.stdin.isatty():
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        return

    try:
        import selectors
        import termios
        import tty
    except ImportError:
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    sel = selectors.DefaultSelector()
    try:
        tty.setcbreak(fd)
        sel.register(sys.stdin, selectors.EVENT_READ)
        while True:
            await asyncio.sleep(0.1)
            for _key, _ in sel.select(timeout=0):
                ch = sys.stdin.read(1)
                if ch in ("q", "Q"):
                    return
    except asyncio.CancelledError:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sel.close()
