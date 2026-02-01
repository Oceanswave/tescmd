"""CLI commands for the MCP (Model Context Protocol) server."""

from __future__ import annotations

import click

from tescmd.cli._options import global_options

mcp_group = click.Group("mcp", help="MCP (Model Context Protocol) server.")


@mcp_group.command("serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "streamable-http"]),
    default="streamable-http",
    help="MCP transport (default: streamable-http)",
)
@click.option("--port", type=int, default=8080, help="HTTP port (streamable-http only)")
@click.option("--tailscale", is_flag=True, default=False, help="Expose via Tailscale Funnel")
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
    transport: str,
    port: int,
    tailscale: bool,
    client_id: str | None,
    client_secret: str | None,
) -> None:
    """Start an MCP server exposing tescmd commands as tools.

    Agents (Claude Desktop, Claude Code, etc.) connect to this server
    and invoke tescmd commands as MCP tools with JSON output.

    \b
    Transports:
      streamable-http  HTTP server on --port (default)
      stdio            Read/write JSON-RPC on stdin/stdout

    \b
    Authentication (required for all transports):
      Set TESCMD_MCP_CLIENT_ID and TESCMD_MCP_CLIENT_SECRET, or pass
      --client-id / --client-secret. HTTP clients authenticate with
      Authorization: Bearer <client-secret>.

    \b
    Examples:
      tescmd mcp serve                          # HTTP on :8080
      tescmd mcp serve --transport stdio        # stdio for Claude Desktop
      tescmd mcp serve --tailscale              # expose via Tailscale Funnel
    """
    from tescmd._internal.async_utils import run_async
    from tescmd.cli.main import AppContext

    assert isinstance(app_ctx, AppContext)

    if not client_id or not client_secret:
        raise click.UsageError(
            "MCP client credentials required.\n"
            "Set TESCMD_MCP_CLIENT_ID and TESCMD_MCP_CLIENT_SECRET "
            "in your .env file or environment, or pass --client-id and --client-secret."
        )

    if tailscale and transport == "stdio":
        raise click.UsageError("--tailscale cannot be used with --transport stdio")

    run_async(_cmd_serve(app_ctx, transport, port, tailscale, client_id, client_secret))


async def _cmd_serve(
    app_ctx: object,
    transport: str,
    port: int,
    tailscale: bool,
    client_id: str,
    client_secret: str,
) -> None:
    import sys

    from tescmd.cli.main import AppContext
    from tescmd.mcp.server import create_mcp_server

    assert isinstance(app_ctx, AppContext)
    formatter = app_ctx.formatter
    server = create_mcp_server(client_id=client_id, client_secret=client_secret)
    tool_count = len(server.list_tools())

    if transport == "stdio":
        # Log to stderr so stdout stays clean for JSON-RPC
        print(f"tescmd MCP server starting (stdio, {tool_count} tools)", file=sys.stderr)
        await server.run_stdio()
        return

    if not tailscale:
        if formatter.format != "json":
            formatter.rich.info(
                f"MCP server starting on http://127.0.0.1:{port}/mcp ({tool_count} tools)"
            )
            formatter.rich.info("Press Ctrl+C to stop.")
        await server.run_http(port=port)
        return

    # Tailscale Funnel mode
    from tescmd.telemetry.tailscale import TailscaleManager

    ts = TailscaleManager()
    await ts.check_available()
    await ts.check_running()

    if formatter.format != "json":
        formatter.rich.info(f"MCP server starting on port {port} ({tool_count} tools)")

    url = await ts.start_funnel(port)
    public_url = f"{url}/mcp"

    if formatter.format != "json":
        formatter.rich.info(f"Tailscale Funnel active: {public_url}")
        formatter.rich.info("Press Ctrl+C to stop.")
    else:
        print(f'{{"url": "{public_url}"}}', file=sys.stderr)

    try:
        await server.run_http(port=port, public_url=url)
    finally:
        await ts.stop_funnel()
        if formatter.format != "json":
            formatter.rich.info("Tailscale Funnel stopped.")
