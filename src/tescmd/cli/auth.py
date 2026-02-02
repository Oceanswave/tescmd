"""CLI commands for authentication (login, logout, status, refresh, export, import, register)."""

from __future__ import annotations

import json
import sys
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import ConfigError
from tescmd.auth.oauth import (
    login_flow,
    refresh_access_token,
    register_partner_account,
)
from tescmd.auth.token_store import TokenStore
from tescmd.cli._options import global_options
from tescmd.models.auth import (
    DEFAULT_SCOPES,
    PARTNER_SCOPES,
    TokenData,
    decode_jwt_payload,
    decode_jwt_scopes,
)
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext
    from tescmd.output.formatter import OutputFormatter

DEVELOPER_PORTAL_URL = "https://developer.tesla.com/dashboard"


# ---------------------------------------------------------------------------
# Command group
# ---------------------------------------------------------------------------

auth_group = click.Group("auth", help="Authentication commands")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@auth_group.command("login")
@click.option(
    "--port",
    type=int,
    default=None,
    help="Local callback port (default: 8085 or TESCMD_OAUTH_PORT)",
)
@click.option(
    "--reconsent",
    is_flag=True,
    default=False,
    help="Force Tesla to re-display the scope consent screen.",
)
@global_options
def login_cmd(app_ctx: AppContext, port: int | None, reconsent: bool) -> None:
    """Log in via OAuth2 PKCE flow."""
    run_async(_cmd_login(app_ctx, port, reconsent=reconsent))


async def _cmd_login(app_ctx: AppContext, port: int | None, *, reconsent: bool = False) -> None:
    from tescmd.models.auth import DEFAULT_PORT

    formatter = app_ctx.formatter
    settings = AppSettings()

    if port is None:
        port = DEFAULT_PORT

    client_id = settings.client_id
    client_secret = settings.client_secret

    redirect_uri = f"http://localhost:{port}/callback"

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

        # Redirect first-run to the setup wizard for a guided experience
        from tescmd.cli.setup import _cmd_setup

        await _cmd_setup(app_ctx)
        return

    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )
    region = app_ctx.region or settings.region

    formatter.rich.info("")
    formatter.rich.info("Opening your browser to sign in to Tesla...")
    formatter.rich.info(
        "When prompted, click [cyan]Select All[/cyan] and then"
        " [cyan]Allow[/cyan] to grant tescmd access."
    )
    formatter.rich.info("[dim]If the browser doesn't open, visit the URL printed below.[/dim]")

    token = await login_flow(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=DEFAULT_SCOPES,
        port=port,
        token_store=store,
        region=region,
        force_consent=reconsent,
    )

    formatter.rich.info("")
    formatter.rich.info("[bold green]Login successful![/bold green]")
    _warn_missing_scopes(formatter, token, requested=DEFAULT_SCOPES)

    # Auto-register with the Fleet API (requires client_secret + domain)
    if client_secret and settings.domain:
        await _auto_register(formatter, client_id, client_secret, settings.domain, region)
    else:
        formatter.rich.info("")
        formatter.rich.info("[yellow]Next step:[/yellow] Register your app with the Fleet API.")
        formatter.rich.info("  [cyan]tescmd auth register[/cyan]")

    formatter.rich.info("")
    formatter.rich.info("Try it out:")
    formatter.rich.info("  [cyan]tescmd vehicle list[/cyan]")
    formatter.rich.info("")


@auth_group.command("logout")
@global_options
def logout_cmd(app_ctx: AppContext) -> None:
    """Clear stored tokens."""
    run_async(_cmd_logout(app_ctx))


async def _cmd_logout(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()
    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )
    store.clear()

    if formatter.format == "json":
        formatter.output({"status": "logged_out"}, command="auth.logout")
    else:
        formatter.rich.info("Tokens cleared.")


@auth_group.command("status")
@global_options
def status_cmd(app_ctx: AppContext) -> None:
    """Show authentication status."""
    run_async(_cmd_status(app_ctx))


async def _cmd_status(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()
    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )

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

    # Decode the JWT to show the *actual* granted scopes and audience
    token_scopes: list[str] | None = None
    audience: str | None = None
    access_token = store.access_token
    if access_token:
        token_scopes = decode_jwt_scopes(access_token)
        jwt_payload = decode_jwt_payload(access_token)
        if jwt_payload is not None:
            aud_raw = jwt_payload.get("aud")
            if isinstance(aud_raw, list) and aud_raw:
                audience = aud_raw[0] if len(aud_raw) == 1 else ", ".join(str(a) for a in aud_raw)
            elif isinstance(aud_raw, str):
                audience = aud_raw
            # Also check for 'ou' (origin URL) — Tesla-specific claim
            ou = jwt_payload.get("ou")
            if isinstance(ou, str) and ou:
                audience = ou

    if formatter.format == "json":
        data: dict[str, object] = {
            "authenticated": True,
            "expires_in": expires_in,
            "scopes": scopes,
            "region": region,
            "has_refresh_token": has_refresh,
        }
        if token_scopes is not None:
            data["token_scopes"] = token_scopes
        if audience is not None:
            data["audience"] = audience
        formatter.output(data, command="auth.status")
    else:
        formatter.rich.info("Authenticated: yes")
        formatter.rich.info(f"Expires in: {expires_in}s")
        formatter.rich.info(f"Scopes (stored): {', '.join(scopes)}")
        if token_scopes is not None:
            formatter.rich.info(f"Scopes (token):  {', '.join(token_scopes)}")
            missing = set(scopes) - set(token_scopes)
            if missing:
                not_granted = ", ".join(sorted(missing))
                formatter.rich.info(
                    f"  [yellow]Warning: requested but not granted: {not_granted}[/yellow]"
                )
        if audience is not None:
            formatter.rich.info(f"Audience: {audience}")
        formatter.rich.info(f"Region: {region}")
        formatter.rich.info(f"Refresh token: {'yes' if has_refresh else 'no'}")


@auth_group.command("refresh")
@global_options
def refresh_cmd(app_ctx: AppContext) -> None:
    """Refresh the access token using the stored refresh token."""
    run_async(_cmd_refresh(app_ctx))


async def _cmd_refresh(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()
    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )

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

    from tescmd.api.errors import AuthError
    from tescmd.cli._client import reauth_on_expired_refresh

    try:
        token_data = await refresh_access_token(
            refresh_token=rt,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
        )
    except AuthError as exc:
        if "login_required" not in str(exc):
            raise
        await reauth_on_expired_refresh(store, settings)
        if formatter.format == "json":
            formatter.output({"status": "re-authenticated"}, command="auth.refresh")
        else:
            formatter.rich.info("")
        return

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


@auth_group.command("export")
@global_options
def export_cmd(app_ctx: AppContext) -> None:
    """Export tokens as JSON to stdout."""
    run_async(_cmd_export(app_ctx))


async def _cmd_export(app_ctx: AppContext) -> None:
    settings = AppSettings()
    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )
    data = store.export_dict()
    print(json.dumps(data, indent=2))


@auth_group.command("register")
@global_options
def register_cmd(app_ctx: AppContext) -> None:
    """Register app with the Fleet API (one-time)."""
    run_async(_cmd_register(app_ctx))


async def _cmd_register(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()

    if not settings.client_id:
        raise ConfigError(
            "TESLA_CLIENT_ID is required. Run 'tescmd auth login' to set up your credentials."
        )
    if not settings.client_secret:
        raise ConfigError(
            "TESLA_CLIENT_SECRET is required for Fleet API registration. "
            "Add it to your .env file or set it as an environment variable."
        )

    region = app_ctx.region or settings.region
    domain = settings.domain

    # Prompt for domain if not configured
    if not domain and formatter.format != "json":
        domain = _prompt_for_domain(formatter)
        if not domain:
            return

    if not domain:
        raise ConfigError(
            "TESLA_DOMAIN is required for Fleet API registration. "
            "Set it in your .env file (e.g. TESLA_DOMAIN=myapp.example.com)."
        )

    if formatter.format != "json":
        formatter.rich.info(f"Registering application with Fleet API ({region} region)...")

    _result, partner_scopes = await register_partner_account(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        domain=domain,
        region=region,
    )

    if formatter.format == "json":
        data: dict[str, object] = {
            "status": "registered",
            "region": region,
            "domain": domain,
        }
        if partner_scopes:
            data["partner_scopes"] = partner_scopes
        formatter.output(data, command="auth.register")
    else:
        formatter.rich.info("[green]Registration successful.[/green]")
        if partner_scopes:
            formatter.rich.info(f"Partner scopes: {', '.join(partner_scopes)}")
            missing = sorted(set(PARTNER_SCOPES) - set(partner_scopes))
            if missing:
                scope_list = ", ".join(missing)
                formatter.rich.info(
                    f"[yellow]Warning: partner token is missing: {scope_list}[/yellow]"
                )
                formatter.rich.info("  These scopes won't be available in user tokens.")
                formatter.rich.info("  Check your Tesla Developer Portal app configuration.")
        formatter.rich.info("")
        formatter.rich.info("Try it out:")
        formatter.rich.info("  [cyan]tescmd vehicle list[/cyan]")
        formatter.rich.info("")


@auth_group.command("import")
@global_options
def import_cmd(app_ctx: AppContext) -> None:
    """Import tokens from JSON on stdin."""
    run_async(_cmd_import(app_ctx))


async def _cmd_import(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()
    raw = sys.stdin.read()
    data = json.loads(raw)
    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )
    store.import_dict(data)

    if formatter.format == "json":
        formatter.output({"status": "imported"}, command="auth.import")
    else:
        formatter.rich.info("Tokens imported successfully.")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _auto_register(
    formatter: OutputFormatter,
    client_id: str,
    client_secret: str,
    domain: str,
    region: str,
) -> None:
    """Attempt Fleet API registration silently after login."""
    formatter.rich.info("")
    formatter.rich.info("Registering with the Fleet API...")
    try:
        _result, partner_scopes = await register_partner_account(
            client_id=client_id,
            client_secret=client_secret,
            domain=domain,
            region=region,
        )
        formatter.rich.info("[green]Registration successful.[/green]")
        if partner_scopes:
            missing = sorted(set(PARTNER_SCOPES) - set(partner_scopes))
            if missing:
                scope_list = ", ".join(missing)
                formatter.rich.info(
                    f"[yellow]Warning: partner token missing scopes: {scope_list}[/yellow]"
                )
    except Exception:
        formatter.rich.info(
            "[yellow]Registration failed. Run [cyan]tescmd auth register[/cyan] to retry.[/yellow]"
        )


def _interactive_setup(
    formatter: OutputFormatter,
    port: int,
    redirect_uri: str,
    *,
    domain: str = "",
    tailscale_hostname: str = "",
) -> tuple[str, str]:
    """Walk the user through first-time Tesla API credential setup.

    When *domain* is provided (e.g. from the setup wizard), the developer
    portal instructions show ``https://{domain}`` as the Allowed Origin URL.
    Tesla's Fleet API requires the origin to match the registration domain.

    When *tailscale_hostname* is provided (or auto-detected), the user is
    offered the chance to start a Tailscale Funnel so Tesla can verify the
    origin URL when the portal app config is saved.
    """
    info = formatter.rich.info
    origin_url = f"https://{domain}" if domain else f"http://localhost:{port}"

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
    info("  Description:       [cyan]Personal CLI tool for vehicle status and control[/cyan]")
    info(
        "  Purpose of Usage:  [cyan]Query vehicle data and send commands from the terminal[/cyan]"
    )
    info("  Click Next.")
    info("")

    # Detect Tailscale and offer to start Funnel for origin URL verification
    ts_hostname = tailscale_hostname
    ts_funnel_started = False
    if not ts_hostname:
        try:
            from tescmd.deploy.tailscale_serve import is_tailscale_serve_ready

            if run_async(is_tailscale_serve_ready()):
                from tescmd.telemetry.tailscale import TailscaleManager

                ts_hostname = run_async(TailscaleManager().get_hostname())
        except Exception:
            pass

    if ts_hostname:
        ts_origin = f"https://{ts_hostname}"
        info("")
        info(f"[green]Tailscale detected:[/green] {ts_hostname}")
        info("")
        info(f"  Adding [cyan]{ts_origin}[/cyan] as an Allowed Origin URL")
        info("  will let [cyan]tescmd serve[/cyan] stream telemetry without")
        info("  extra portal changes later.")
        info("")
        try:
            answer = input("Start Tailscale Funnel so Tesla can verify the URL? [Y/n] ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer.lower() != "n":
            info("Starting Tailscale Funnel...")
            try:
                from tescmd.telemetry.tailscale import TailscaleManager as _TsMgr

                run_async(_TsMgr().enable_funnel())
                ts_funnel_started = True
                info(f"[green]Funnel active — {ts_origin} is reachable.[/green]")
            except Exception as exc:
                info(f"[yellow]Could not start Funnel: {exc}[/yellow]")
                info("[dim]You can add the origin URL manually later.[/dim]")
                ts_hostname = ""

    # Step 3 — Client Details
    info("[bold]Step 3 — Client Details[/bold]")
    info(
        "  OAuth Grant Type:    [cyan]Authorization Code and"
        " Machine-to-Machine[/cyan]  (the default)"
    )
    info(f"  Allowed Origin URL:  [cyan]{origin_url}[/cyan]")
    if ts_hostname:
        info(f"  [bold]Also add:[/bold]          [cyan]https://{ts_hostname}[/cyan]")
    info(f"  Allowed Redirect URI: [cyan]{redirect_uri}[/cyan]")
    info("  Allowed Returned URL: (leave empty)")
    info("")
    if not ts_hostname:
        info(
            "  [dim]For telemetry streaming, add your Tailscale hostname"
            " as an additional origin:[/dim]"
        )
        info("  [dim]  https://<machine>.tailnet.ts.net[/dim]")
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
    info(
        "  Open your dashboard:"
        " [link=https://developer.tesla.com/en_US/dashboard]"
        "developer.tesla.com/dashboard[/link]"
    )
    info("  Click [cyan]View Details[/cyan] on your app.")
    info("  Under the [cyan]Credentials & APIs[/cyan] tab you'll see your")
    info("  Client ID (copy icon) and Client Secret (eye icon to reveal).")
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
        client_secret = input("Client Secret (optional, press Enter to skip): ").strip()
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

    # Clean up Tailscale Funnel if we started it during this session
    if ts_funnel_started:
        try:
            from tescmd.telemetry.tailscale import TailscaleManager as _TsMgr

            run_async(_TsMgr._run("tailscale", "funnel", "--bg", "off"))
        except Exception as exc:
            info(f"[yellow]Warning: Failed to stop Tailscale Funnel: {exc}[/yellow]")
            info("[dim]You may need to run 'tailscale funnel --bg off' manually.[/dim]")

    info("")
    return (client_id, client_secret)


def _prompt_for_domain(formatter: OutputFormatter) -> str:
    """Prompt the user for a domain to use for Fleet API registration."""
    info = formatter.rich.info
    info("")
    info("Tesla requires a [bold]registered domain[/bold] to activate your Fleet API access.")
    info("")
    info("  The easiest option is a free [cyan]GitHub Pages[/cyan] site:")
    info("  1. Create a public repo named [cyan]<username>.github.io[/cyan]")
    info("  2. Enable GitHub Pages in the repo settings")
    info("  3. Enter [cyan]<username>.github.io[/cyan] as your domain below")
    info("")
    info(
        "[dim]Any domain you control works. For vehicle commands"
        " (post-MVP) you'll also host a public key there.[/dim]"
    )
    info("")

    try:
        domain = input("Domain (e.g. yourname.github.io): ").strip()
    except (EOFError, KeyboardInterrupt):
        info("")
        return ""

    if not domain:
        info("[yellow]No domain provided. Registration cancelled.[/yellow]")
        return ""

    # Strip protocol if user included it
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix) :]
            break

    # Strip trailing slash and lowercase (Tesla Fleet API rejects uppercase)
    domain = domain.rstrip("/").lower()

    # Save domain to .env for future use
    _write_env_value("TESLA_DOMAIN", domain)
    info(f"[green]Domain saved to .env: {domain}[/green]")

    return domain


def _warn_missing_scopes(
    formatter: OutputFormatter,
    token: TokenData,
    *,
    requested: list[str],
) -> None:
    """Warn the user if the token has fewer scopes than requested."""
    granted = decode_jwt_scopes(token.access_token)
    if granted is None:
        return

    # offline_access is a token-lifetime directive, not present in JWTs
    requested_set = {s for s in requested if s != "offline_access"}
    missing = sorted(requested_set - set(granted))
    if not missing:
        return

    scope_list = ", ".join(missing)
    if formatter.format == "json":
        formatter.output(
            {
                "warning": "missing_scopes",
                "missing": missing,
                "message": (
                    f"Token is missing requested scopes: {scope_list}. "
                    "Run 'tescmd auth login --reconsent' to re-approve scopes."
                ),
            },
            command="auth.login",
        )
    else:
        formatter.rich.info("")
        formatter.rich.info(f"[yellow]Warning: token is missing scopes: {scope_list}[/yellow]")
        formatter.rich.info("  Tesla is using a cached consent that predates these scopes.")
        formatter.rich.info(
            "  Run [cyan]tescmd auth login --reconsent[/cyan] to re-approve all scopes."
        )


def _write_env_file(
    client_id: str,
    client_secret: str,
    domain: str = "",
) -> None:
    """Write Tesla API credentials to a ``.env`` file in the working directory."""
    values: dict[str, str] = {"TESLA_CLIENT_ID": client_id}
    if client_secret:
        values["TESLA_CLIENT_SECRET"] = client_secret
    if domain:
        values["TESLA_DOMAIN"] = domain

    env_path = Path(".env")
    lines: list[str] = []

    if env_path.exists():
        existing = env_path.read_text()
        for line in existing.splitlines():
            stripped = line.strip()
            if any(stripped.startswith(f"{k}=") for k in values):
                continue
            lines.append(line)
        if lines and lines[-1] != "":
            lines.append("")

    for key, val in values.items():
        lines.append(f"{key}={val}")
    lines.append("")

    env_path.write_text("\n".join(lines))


def _write_env_value(key: str, value: str) -> None:
    """Write or update a single key in the ``.env`` file."""
    env_path = Path(".env")
    lines: list[str] = []

    if env_path.exists():
        existing = env_path.read_text()
        for line in existing.splitlines():
            if line.strip().startswith(f"{key}="):
                continue
            lines.append(line)
        if lines and lines[-1] != "":
            lines.append("")

    lines.append(f"{key}={value}")
    lines.append("")

    env_path.write_text("\n".join(lines))
