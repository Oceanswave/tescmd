"""Unified ``tescmd serve`` command — MCP + telemetry cache warming + optional OpenClaw."""

from __future__ import annotations

import logging
import random
import signal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio

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
@click.option(
    "--port",
    type=int,
    default=8080,
    envvar="TESCMD_MCP_PORT",
    help="MCP HTTP port (streamable-http only)",
)
@click.option(
    "--host",
    default="127.0.0.1",
    envvar="TESCMD_HOST",
    help="Bind address (default: 127.0.0.1)",
)
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
    host: str,
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
            mcp_host=host,
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
    mcp_host: str = "127.0.0.1",
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
    is_rich = formatter.format != "json"

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
    oc_bridge = None
    dashboard = None
    tui = None
    trigger_manager = None
    vin: str | None = None
    field_config: dict[str, dict[str, int]] | None = None

    if not no_telemetry:
        from tescmd.cli._client import get_cache
        from tescmd.telemetry.cache_sink import CacheSink
        from tescmd.telemetry.fields import resolve_fields
        from tescmd.telemetry.mapper import TelemetryMapper

        vin = require_vin(vin_positional, app_ctx.vin)

        from tescmd.triggers.manager import TriggerManager

        trigger_manager = TriggerManager(vin=vin)

        if telemetry_port is None:
            telemetry_port = random.randint(49152, 65534)

        field_config = resolve_fields(fields_spec, interval_override)

        # Cache sink — warms the response cache from telemetry
        cache = get_cache(app_ctx)
        mapper = TelemetryMapper()
        cache_sink = CacheSink(cache, mapper, vin)
        fanout.add_sink(cache_sink.on_frame)

        if is_rich:
            formatter.rich.info(f"Cache warming enabled for {vin}")

        # CSV log sink — wide-format telemetry log (default on)
        if not no_log:
            from tescmd.telemetry.csv_sink import CSVLogSink, create_log_path

            csv_path = create_log_path(vin)
            csv_sink = CSVLogSink(csv_path, vin=vin)
            fanout.add_sink(csv_sink.on_frame)

            if is_rich:
                formatter.rich.info(f"CSV log: {csv_path}")

        # Display sink: TUI (default) / legacy Rich.Live dashboard / JSONL
        if interactive and is_rich:
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

            from tescmd.openclaw.bridge import build_openclaw_pipeline
            from tescmd.openclaw.config import BridgeConfig

            if openclaw_config_path:
                config = BridgeConfig.load(Path(openclaw_config_path))
            else:
                config = BridgeConfig.load()
            config = config.merge_overrides(
                gateway_url=openclaw_url,
                gateway_token=openclaw_token,
            )
            oc_pipeline = build_openclaw_pipeline(
                config, vin, app_ctx, trigger_manager=trigger_manager, dry_run=dry_run
            )
            gw = oc_pipeline.gateway
            oc_bridge = oc_pipeline.bridge

            # Push trigger notifications to gateway
            if trigger_manager is not None:
                push_cb = oc_bridge.make_trigger_push_callback()
                if push_cb is not None:
                    trigger_manager.add_on_fire(push_cb)

            if not dry_run:
                if is_rich:
                    formatter.rich.info(f"Connecting to OpenClaw Gateway: {config.gateway_url}")
                await gw.connect_with_backoff(max_attempts=5)
                if is_rich:
                    formatter.rich.info("[green]Connected to OpenClaw gateway.[/green]")
            else:
                if is_rich:
                    formatter.rich.info(
                        "[yellow]Dry-run mode — events will be logged as JSONL to stderr.[/yellow]"
                    )

            # Register sink AFTER gateway is connected (or dry-run confirmed)
            # so early telemetry frames aren't silently dropped.
            fanout.add_sink(oc_bridge.on_frame)

        # Lightweight trigger sink — evaluates triggers when there is no
        # OpenClaw bridge (which handles evaluation itself).
        if trigger_manager is not None and not openclaw_url:
            from tescmd.openclaw.telemetry_store import TelemetryStore as _TStore

            _trigger_store = _TStore()

            async def _trigger_sink(frame: object) -> None:
                from tescmd.telemetry.decoder import TelemetryFrame

                assert isinstance(frame, TelemetryFrame)
                assert trigger_manager is not None
                for datum in frame.data:
                    prev_snap = _trigger_store.get(datum.field_name)
                    prev_value = prev_snap.value if prev_snap is not None else None
                    _trigger_store.update(datum.field_name, datum.value, frame.created_at)
                    await trigger_manager.evaluate(
                        datum.field_name, datum.value, prev_value, frame.created_at
                    )

            fanout.add_sink(_trigger_sink)

    # -- Register MCP trigger tools (when both MCP and telemetry are active) --
    if mcp_server is not None and trigger_manager is not None:
        _register_trigger_tools(mcp_server, trigger_manager)
        tool_count = len(mcp_server.list_tools())

    # -- Tailscale Funnel setup (optional, MCP-only mode) --
    public_url: str | None = None
    ts = None
    if tailscale and no_telemetry and not no_mcp:
        # MCP-only with --tailscale: funnel directly to MCP port.
        # When telemetry is active the funnel is managed by
        # telemetry_session (pointing to the combined app port).
        from tescmd.telemetry.tailscale import TailscaleManager

        ts = TailscaleManager()
        await ts.check_available()
        await ts.check_running()
        funnel_url = await ts.start_funnel(mcp_port)
        public_url = funnel_url

        if is_rich:
            formatter.rich.info(f"Tailscale Funnel active: {funnel_url}/mcp")
        else:
            print(f'{{"url": "{funnel_url}/mcp"}}', file=sys.stderr)

    # -- Combined mode: pre-determine tunnel hostname for MCP public_url --
    # When both MCP and telemetry are active, telemetry_session will start
    # a Tailscale Funnel.  We need the hostname NOW so the MCP app's auth
    # settings (issuer_url) are correct before the app is built.
    if not no_telemetry and not no_mcp and public_url is None:
        try:
            from tescmd.telemetry.tailscale import TailscaleManager

            _ts_pre = TailscaleManager()
            await _ts_pre.check_available()
            await _ts_pre.check_running()
            _pre_hostname = await _ts_pre.get_hostname()
            public_url = f"https://{_pre_hostname}"
        except Exception:
            logger.warning("Tailscale auto-detection failed — using localhost")

    # -- Populate TUI with server info --
    if tui is not None:
        mcp_url = ""
        if not no_mcp:
            mcp_url = f"{public_url}/mcp" if public_url else f"http://{mcp_host}:{mcp_port}/mcp"
            tui.set_mcp_url(mcp_url)
        if public_url:
            tui.set_tunnel_url(public_url)
        tui.set_sink_count(fanout.sink_count)
        if csv_sink is not None:
            tui.set_log_path(csv_sink.log_path)

    # -- Start everything --
    if not no_mcp and is_rich and tui is None:
        base_url = f"{public_url}/mcp" if public_url else f"http://{mcp_host}:{mcp_port}/mcp"
        formatter.rich.info(
            f"MCP server starting on {base_url} ({tool_count} tools, "
            f"{fanout.sink_count} telemetry sink(s))"
        )
    if (not no_mcp or not no_telemetry) and is_rich and tui is None:
        formatter.rich.info("Press Ctrl+C to stop.")

    # -- SIGTERM handler for graceful container/systemd shutdown --
    shutdown_event = asyncio.Event()

    def _handle_sigterm() -> None:
        logger.info("SIGTERM received — shutting down gracefully")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    # Only add signal handler on Unix (Windows doesn't support loop.add_signal_handler)
    if hasattr(signal, "SIGTERM"):
        import contextlib

        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signal.SIGTERM, _handle_sigterm)

    combined_task: asyncio.Task[None] | None = None
    _uvi_server: Any = None  # uvicorn.Server — for graceful shutdown
    try:
        if fanout.has_sinks() and vin is not None and field_config is not None:
            from tescmd.telemetry.setup import telemetry_session

            assert telemetry_port is not None

            # When MCP is co-located, build a combined Starlette app
            # that serves MCP (HTTP/auth) and telemetry (WebSocket) on
            # the same port so a single Tailscale Funnel covers both.
            combined_app = None
            serve_port = telemetry_port
            if mcp_server is not None:
                from pathlib import Path

                import uvicorn

                from tescmd.crypto.keys import load_public_key_pem
                from tescmd.models.config import AppSettings

                _app_settings = AppSettings()
                _key_dir = Path(_app_settings.config_dir).expanduser() / "keys"
                _pub_pem = load_public_key_pem(_key_dir)

                combined_app = _build_combined_app(
                    mcp_server, mcp_port, public_url, fanout.on_frame, _pub_pem
                )
                serve_port = mcp_port

                # Start the combined app BEFORE telemetry_session so that
                # Tesla's domain-verification HEAD requests (during partner
                # registration inside the session) hit a running server.
                # Keep a handle on the uvicorn.Server so we can signal a
                # graceful shutdown (should_exit) instead of cancelling.
                _uvi_cfg = uvicorn.Config(
                    combined_app, host=mcp_host, port=mcp_port, log_level="warning"
                )
                _uvi_server = uvicorn.Server(_uvi_cfg)
                combined_task = asyncio.create_task(_uvi_server.serve())
                # Give uvicorn a moment to bind the port.
                await asyncio.sleep(0.5)
                if combined_task.done():
                    exc = combined_task.exception()
                    if exc is not None:
                        raise OSError(f"Failed to start server on port {mcp_port}: {exc}") from exc

            try:
                async with telemetry_session(
                    app_ctx,
                    vin,
                    serve_port,
                    field_config,
                    fanout.on_frame,
                    interactive=interactive,
                    skip_server=(combined_task is not None),
                ) as session:
                    if tui is not None:
                        tui.set_tunnel_url(session.tunnel_url)

                    if is_rich and tui is None:
                        formatter.rich.info("Telemetry pipeline active.")

                    if tui is not None:
                        await _race_shutdown(tui.run_async(), shutdown_event)
                    elif dashboard is not None:
                        from rich.live import Live

                        dashboard.set_tunnel_url(session.tunnel_url)
                        with Live(
                            dashboard,
                            console=formatter.console,
                            refresh_per_second=4,
                        ) as live:
                            dashboard.set_live(live)
                            await _wait_for_interrupt(shutdown_event)
                    else:
                        await _wait_for_interrupt(shutdown_event)
            finally:
                # Signal uvicorn to shut down gracefully rather than
                # cancelling (which causes a CancelledError traceback
                # inside Starlette's lifespan handler).
                if _uvi_server is not None:
                    _uvi_server.should_exit = True
                if combined_task is not None and not combined_task.done():
                    with contextlib.suppress(asyncio.CancelledError):
                        await combined_task
        elif mcp_server is not None:
            await _race_shutdown(
                mcp_server.run_http(host=mcp_host, port=mcp_port, public_url=public_url),
                shutdown_event,
            )
    finally:
        if ts is not None:
            await ts.stop_funnel()
            if is_rich:
                formatter.rich.info("Tailscale Funnel stopped.")
        if oc_bridge is not None:
            await oc_bridge.send_disconnecting()
        if gw is not None:
            await gw.close()
        if csv_sink is not None:
            csv_sink.close()
            if is_rich:
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
            if cmd_log and is_rich:
                formatter.rich.info(f"[dim]Command log: {cmd_log}[/dim]")
            activity_log = getattr(tui, "_activity_log_path", "")
            if activity_log and is_rich:
                formatter.rich.info(f"[dim]Activity log: {activity_log}[/dim]")
        if cache_sink is not None:
            cache_sink.flush()
            if is_rich:
                formatter.rich.info(
                    f"[dim]Cache sink: {cache_sink.frame_count} frames, "
                    f"{cache_sink.field_count} field updates[/dim]"
                )


def _register_trigger_tools(mcp_server: Any, trigger_manager: Any) -> None:
    """Register trigger CRUD tools on the MCP server."""
    from tescmd.triggers.models import TriggerCondition, TriggerDefinition, TriggerOperator

    def _handle_create(params: dict[str, Any]) -> dict[str, Any]:
        field = params.get("field")
        if not field:
            raise ValueError("trigger_create requires 'field' parameter")
        op_str = params.get("operator")
        if not op_str:
            raise ValueError("trigger_create requires 'operator' parameter")
        condition = TriggerCondition(
            field=field,
            operator=TriggerOperator(op_str),
            value=params.get("value"),
        )
        trigger = TriggerDefinition(
            condition=condition,
            once=params.get("once", False),
            cooldown_seconds=params.get("cooldown_seconds", 60.0),
        )
        created = trigger_manager.create(trigger)
        return created.model_dump(mode="json")

    def _handle_delete(params: dict[str, Any]) -> dict[str, Any]:
        trigger_id = params.get("id")
        if not trigger_id:
            raise ValueError("trigger_delete requires 'id' parameter")
        deleted = trigger_manager.delete(trigger_id)
        return {"deleted": deleted, "id": trigger_id}

    def _handle_list(params: dict[str, Any]) -> dict[str, Any]:
        triggers = trigger_manager.list_all()
        return {"triggers": [t.model_dump(mode="json") for t in triggers]}

    def _handle_poll(params: dict[str, Any]) -> dict[str, Any]:
        notifications = trigger_manager.drain_pending()
        return {"notifications": [n.model_dump(mode="json") for n in notifications]}

    mcp_server.register_custom_tool(
        "trigger_create",
        _handle_create,
        "Create a telemetry trigger condition",
        {
            "type": "object",
            "properties": {
                "field": {"type": "string", "description": "Telemetry field name"},
                "operator": {
                    "type": "string",
                    "description": "Operator: lt, gt, lte, gte, eq, neq, changed, enter, leave",
                },
                "value": {"description": "Threshold value (optional for 'changed')"},
                "once": {
                    "type": "boolean",
                    "description": "Fire once then auto-delete (default: false)",
                },
                "cooldown_seconds": {
                    "type": "number",
                    "description": "Cooldown between firings (default: 60)",
                },
            },
            "required": ["field", "operator"],
        },
        is_write=True,
    )
    mcp_server.register_custom_tool(
        "trigger_delete",
        _handle_delete,
        "Delete a telemetry trigger by ID",
        {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Trigger ID"}},
            "required": ["id"],
        },
        is_write=True,
    )
    mcp_server.register_custom_tool(
        "trigger_list",
        _handle_list,
        "List all active telemetry triggers",
        {"type": "object", "properties": {}},
    )
    mcp_server.register_custom_tool(
        "trigger_poll",
        _handle_poll,
        "Poll for fired trigger notifications",
        {"type": "object", "properties": {}},
    )


class _LoggingASGI:
    """Thin ASGI wrapper that logs every HTTP and WebSocket request."""

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            method = scope.get("method", "?")
            path = scope.get("path", "/")
            status: int | None = None

            async def _logging_send(message: Any) -> None:
                nonlocal status
                if message.get("type") == "http.response.start":
                    status = message.get("status")
                await send(message)

            logger.info("HTTP %s %s", method, path)
            await self._app(scope, receive, _logging_send)
            if status is not None:
                logger.info("HTTP %s %s → %d", method, path, status)
        elif scope["type"] == "websocket":
            logger.info("WS  %s", scope.get("path", "/"))
            await self._app(scope, receive, send)
        else:
            # lifespan, etc.
            await self._app(scope, receive, send)


def _build_combined_app(
    mcp_server: object,
    mcp_port: int,
    public_url: str | None,
    on_frame: object,
    public_key_pem: str | None = None,
) -> Any:
    """Build an ASGI app combining MCP (HTTP/auth) and telemetry (WebSocket).

    Uses a raw ASGI dispatcher instead of Starlette ``Mount`` so the MCP
    app receives requests with an **unmodified scope**.  ``Mount`` rewrites
    ``scope["path"]`` and ``scope["root_path"]``, which breaks the MCP
    SDK's internal middleware (transport-security validation, session
    manager lookup, SSE streaming).

    Dispatch order:

    1. ``lifespan`` → forwarded to the MCP app (initialises the session
       manager's task group).
    2. ``websocket`` at ``/`` → Tesla Fleet Telemetry binary frames.
    3. ``http GET/HEAD /.well-known/…/public-key.pem`` → EC public key.
    4. ``http HEAD *`` → fast 200 (Tesla domain validation).
    5. Everything else → MCP app (``/authorize``, ``/token``, ``/mcp``, …).
    """
    from starlette.responses import Response
    from starlette.websockets import WebSocket, WebSocketDisconnect

    from tescmd.mcp.server import MCPServer
    from tescmd.telemetry.decoder import TelemetryDecoder

    assert isinstance(mcp_server, MCPServer)
    mcp_app = mcp_server.create_http_app(port=mcp_port, public_url=public_url)
    decoder = TelemetryDecoder()
    _well_known = "/.well-known/appspecific/com.tesla.3p.public-key.pem"

    async def _app(scope: Any, receive: Any, send: Any) -> None:
        # 1. Lifespan — forwarded so the MCP session manager starts.
        if scope["type"] == "lifespan":
            await mcp_app(scope, receive, send)
            return

        # 2. Tesla telemetry WebSocket at root path.
        if scope["type"] == "websocket" and scope.get("path", "/") == "/":
            websocket = WebSocket(scope, receive, send)
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_bytes()
                    try:
                        frame = decoder.decode(data)
                    except Exception:
                        logger.warning(
                            "Failed to decode telemetry frame (%d bytes) — skipping",
                            len(data),
                            exc_info=True,
                        )
                        continue
                    try:
                        await on_frame(frame)  # type: ignore[operator]
                    except Exception:
                        logger.warning(
                            "Failed to process telemetry frame — skipping",
                            exc_info=True,
                        )
            except WebSocketDisconnect:
                pass
            except Exception:
                logger.debug("WS closed", exc_info=True)
            return

        if scope["type"] == "http":
            method = scope.get("method", "")
            path = scope.get("path", "/")

            # 3. Tesla public-key endpoint.
            if path == _well_known and method in ("GET", "HEAD"):
                if public_key_pem:
                    resp = Response(content=public_key_pem, media_type="application/x-pem-file")
                else:
                    resp = Response(status_code=404)
                await resp(scope, receive, send)
                return

            # 4. Fast 200 for HEAD — Tesla domain validation.
            if method == "HEAD":
                await Response(status_code=200)(scope, receive, send)
                return

        # 5. Everything else → MCP app (scope passed through unmodified).
        await mcp_app(scope, receive, send)

    return _LoggingASGI(_app)


async def _wait_for_interrupt(shutdown_event: asyncio.Event | None = None) -> None:
    """Block until Ctrl+C, 'q' is pressed, or *shutdown_event* is set."""
    import asyncio
    import sys

    def _should_stop() -> bool:
        return shutdown_event is not None and shutdown_event.is_set()

    if not sys.stdin.isatty():
        try:
            while not _should_stop():
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
            while not _should_stop():
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
        while not _should_stop():
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


async def _race_shutdown(
    coro: Any,
    shutdown_event: asyncio.Event,
) -> None:
    """Run *coro* but return early if *shutdown_event* fires (SIGTERM)."""
    import asyncio

    task = asyncio.ensure_future(coro)
    shutdown_waiter = asyncio.create_task(shutdown_event.wait())
    done, pending = await asyncio.wait(
        [task, shutdown_waiter],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
    # Re-raise exceptions from the main task if it finished with an error.
    for t in done:
        if t is not shutdown_waiter:
            t.result()
