"""CLI commands for authentication (login, logout, status, refresh, export, import)."""

from __future__ import annotations

import json
import sys
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

from tescmd.api.errors import ConfigError
from tescmd.auth.oauth import login_flow, refresh_access_token
from tescmd.auth.token_store import TokenStore
from tescmd.models.auth import DEFAULT_SCOPES
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    import argparse

    from tescmd.output.formatter import OutputFormatter

DEVELOPER_PORTAL_URL = "https://developer.tesla.com"


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``auth`` command group and its sub-commands."""
    auth_parser = subparsers.add_parser("auth", help="Authentication commands")
    auth_sub = auth_parser.add_subparsers(dest="subcommand")

    # -- login ---------------------------------------------------------------
    login_p = auth_sub.add_parser("login", help="Log in via OAuth2 PKCE flow")
    login_p.add_argument("--port", type=int, default=8085, help="Local callback port")
    login_p.set_defaults(func=cmd_login)

    # -- logout --------------------------------------------------------------
    logout_p = auth_sub.add_parser("logout", help="Clear stored tokens")
    logout_p.set_defaults(func=cmd_logout)

    # -- status --------------------------------------------------------------
    status_p = auth_sub.add_parser("status", help="Show authentication status")
    status_p.set_defaults(func=cmd_status)

    # -- refresh -------------------------------------------------------------
    refresh_p = auth_sub.add_parser("refresh", help="Refresh the access token")
    refresh_p.set_defaults(func=cmd_refresh)

    # -- export --------------------------------------------------------------
    export_p = auth_sub.add_parser("export", help="Export tokens as JSON to stdout")
    export_p.set_defaults(func=cmd_export)

    # -- import --------------------------------------------------------------
    import_p = auth_sub.add_parser("import", help="Import tokens from JSON on stdin")
    import_p.set_defaults(func=cmd_import)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_login(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Run the interactive OAuth2 login flow."""
    settings = AppSettings()

    client_id = settings.client_id
    client_secret = settings.client_secret

    redirect_uri = f"http://localhost:{args.port}/callback"

    if not client_id:
        if formatter.format == "json":
            formatter.output_error(
                code="missing_client_id",
                message=(
                    "TESLA_CLIENT_ID is not set. Register an application at"
                    " https://developer.tesla.com and set TESLA_CLIENT_ID"
                    " in your environment or .env file."
                ),
                command="auth.login",
            )
            return

        client_id, client_secret = _interactive_setup(
            formatter, args, redirect_uri
        )
        if not client_id:
            return

    store = TokenStore(profile=getattr(args, "profile", "default"))
    region = getattr(args, "region", None) or settings.region

    formatter.rich.info("")
    formatter.rich.info("Opening your browser to sign in to Tesla...")
    formatter.rich.info(
        "[dim]If the browser doesn't open, visit the URL printed below.[/dim]"
    )

    await login_flow(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=DEFAULT_SCOPES,
        port=args.port,
        token_store=store,
        region=region,
    )

    formatter.rich.info("")
    formatter.rich.info("[bold green]Login successful![/bold green]")
    formatter.rich.info("")
    formatter.rich.info("Try it out:")
    formatter.rich.info("  [cyan]tescmd vehicle list[/cyan]")
    formatter.rich.info("")


async def cmd_logout(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Clear all stored tokens."""
    store = TokenStore(profile=getattr(args, "profile", "default"))
    store.clear()

    if formatter.format == "json":
        formatter.output({"status": "logged_out"}, command="auth.logout")
    else:
        formatter.rich.info("Tokens cleared.")


async def cmd_status(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Display current authentication status."""
    store = TokenStore(profile=getattr(args, "profile", "default"))

    if not store.has_token:
        if formatter.format == "json":
            formatter.output({"authenticated": False}, command="auth.status")
        else:
            formatter.rich.info("Not logged in.")
        return

    meta = store.metadata or {}
    expires_at = meta.get("expires_at", 0.0)
    now = time.time()
    expires_in = max(0, int(expires_at - now))
    scopes: list[str] = meta.get("scopes", [])
    region: str = meta.get("region", "unknown")
    has_refresh = store.refresh_token is not None

    if formatter.format == "json":
        formatter.output(
            {
                "authenticated": True,
                "expires_in": expires_in,
                "scopes": scopes,
                "region": region,
                "has_refresh_token": has_refresh,
            },
            command="auth.status",
        )
    else:
        formatter.rich.info("Authenticated: yes")
        formatter.rich.info(f"Expires in: {expires_in}s")
        formatter.rich.info(f"Scopes: {', '.join(scopes)}")
        formatter.rich.info(f"Region: {region}")
        formatter.rich.info(f"Refresh token: {'yes' if has_refresh else 'no'}")


async def cmd_refresh(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Refresh the access token using the stored refresh token."""
    settings = AppSettings()
    store = TokenStore(profile=getattr(args, "profile", "default"))

    rt = store.refresh_token
    if not rt:
        raise ConfigError("No refresh token found. Run 'tescmd auth login' first.")

    if not settings.client_id:
        raise ConfigError(
            "TESLA_CLIENT_ID is required for token refresh. "
            "Add it to your .env file or set it as an environment variable."
        )

    meta = store.metadata or {}
    scopes: list[str] = meta.get("scopes", DEFAULT_SCOPES)
    region: str = meta.get("region", "na")

    token_data = await refresh_access_token(
        refresh_token=rt,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
    )

    store.save(
        access_token=token_data.access_token,
        refresh_token=token_data.refresh_token or rt,
        expires_at=time.time() + token_data.expires_in,
        scopes=scopes,
        region=region,
    )

    if formatter.format == "json":
        formatter.output({"status": "refreshed"}, command="auth.refresh")
    else:
        formatter.rich.info("Token refreshed successfully.")


async def cmd_export(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Export tokens as JSON to stdout."""
    store = TokenStore(profile=getattr(args, "profile", "default"))
    data = store.export_dict()
    print(json.dumps(data, indent=2))


async def cmd_import(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Import tokens from JSON on stdin."""
    raw = sys.stdin.read()
    data = json.loads(raw)
    store = TokenStore(profile=getattr(args, "profile", "default"))
    store.import_dict(data)

    if formatter.format == "json":
        formatter.output({"status": "imported"}, command="auth.import")
    else:
        formatter.rich.info("Tokens imported successfully.")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _interactive_setup(
    formatter: OutputFormatter,
    args: argparse.Namespace,
    redirect_uri: str,
) -> tuple[str, str]:
    """Walk the user through first-time Tesla API credential setup."""
    info = formatter.rich.info
    origin_url = f"http://localhost:{args.port}"

    info("")
    info("[bold cyan]Welcome to tescmd![/bold cyan]")
    info("")
    info(
        "To talk to your Tesla you need API credentials from the"
        " Tesla Developer Portal. This wizard will walk you through it."
    )
    info("")

    # Offer to open the developer portal
    try:
        answer = input("Open the Tesla Developer Portal in your browser? [Y/n] ")
    except (EOFError, KeyboardInterrupt):
        info("")
        return ("", "")

    if answer.strip().lower() != "n":
        webbrowser.open(DEVELOPER_PORTAL_URL)
        info("[dim]Browser opened.[/dim]")

    info("")
    info(
        "Follow these steps to create a Fleet API application."
        " If you already have one, skip to the credentials prompt below."
    )
    info("")

    # Step 1 — Registration
    info("[bold]Step 1 — Registration[/bold]")
    info("  Select [cyan]Just for me[/cyan] and click Next.")
    info("")

    # Step 2 — Application Details
    info("[bold]Step 2 — Application Details[/bold]")
    info("  Application Name:  [cyan]tescmd[/cyan]  (or anything you like)")
    info("  Description:       [cyan]Command line based automation[/cyan]")
    info("  Purpose of Usage:  [cyan]Command line based automation[/cyan]")
    info("  Click Next.")
    info("")

    # Step 3 — Client Details
    info("[bold]Step 3 — Client Details[/bold]")
    info(
        "  OAuth Grant Type:    [cyan]Authorization Code and"
        " Machine-to-Machine[/cyan]  (the default)"
    )
    info(f"  Allowed Origin URL:  [cyan]{origin_url}[/cyan]")
    info(f"  Allowed Redirect URI: [cyan]{redirect_uri}[/cyan]")
    info("  Allowed Returned URL: (leave empty)")
    info("  Click Next.")
    info("")

    # Step 4 — API & Scopes
    info("[bold]Step 4 — API & Scopes[/bold]")
    info("  Under [bold]Fleet API[/bold], check at least:")
    info("    [cyan]Vehicle Information[/cyan]")
    info("    [cyan]Vehicle Location[/cyan]")
    info("    [cyan]Vehicle Commands[/cyan]")
    info("    [cyan]Vehicle Charging Management[/cyan]")
    info("  Click Next.")
    info("")

    # Step 5 — Billing Details
    info("[bold]Step 5 — Billing Details[/bold]")
    info("  Click [cyan]Skip and Submit[/cyan] at the bottom of the page.")
    info("")

    # Post-creation
    info("[bold]Step 6 — Copy your credentials[/bold]")
    info("  Back on Developer Applications, click [cyan]View Details[/cyan]")
    info("  on your new app. Under the [cyan]Credentials & APIs[/cyan] tab")
    info("  you'll see your Client ID (copy icon) and Client Secret")
    info("  (click the eye icon to reveal).")
    info("")

    # Prompt for Client ID
    try:
        client_id = input("Client ID: ").strip()
    except (EOFError, KeyboardInterrupt):
        info("")
        return ("", "")

    if not client_id:
        info("[yellow]No Client ID provided. Setup cancelled.[/yellow]")
        return ("", "")

    # Prompt for Client Secret (optional for public clients)
    try:
        client_secret = input(
            "Client Secret (optional, press Enter to skip): "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        info("")
        return ("", "")

    # Offer to persist credentials to .env
    info("")
    try:
        save = input("Save credentials to .env file? [Y/n] ")
    except (EOFError, KeyboardInterrupt):
        info("")
        return (client_id, client_secret)

    if save.strip().lower() != "n":
        _write_env_file(client_id, client_secret)
        info("[green]Credentials saved to .env[/green]")

    info("")
    return (client_id, client_secret)


def _write_env_file(client_id: str, client_secret: str) -> None:
    """Write Tesla API credentials to a ``.env`` file in the working directory."""
    env_path = Path(".env")
    lines: list[str] = []

    if env_path.exists():
        existing = env_path.read_text()
        for line in existing.splitlines():
            stripped = line.strip()
            if stripped.startswith(("TESLA_CLIENT_ID=", "TESLA_CLIENT_SECRET=")):
                continue
            lines.append(line)
        if lines and lines[-1] != "":
            lines.append("")

    lines.append(f"TESLA_CLIENT_ID={client_id}")
    if client_secret:
        lines.append(f"TESLA_CLIENT_SECRET={client_secret}")
    lines.append("")

    env_path.write_text("\n".join(lines))
