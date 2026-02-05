"""CLI entry-point: Click command group and dispatch."""

from __future__ import annotations

import dataclasses
import logging

import click
from dotenv import load_dotenv

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import (
    AuthError,
    KeyNotEnrolledError,
    MissingScopesError,
    RegistrationRequiredError,
    SessionError,
    TierError,
    TunnelError,
    VehicleAsleepError,
)
from tescmd.output.formatter import OutputFormatter

# ---------------------------------------------------------------------------
# Application context (stored in ctx.obj)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AppContext:
    """Shared state passed to every Click command via ``@click.pass_obj``."""

    vin: str | None
    profile: str
    output_format: str | None
    quiet: bool
    region: str | None
    verbose: bool
    no_cache: bool = False
    auto_wake: bool = False
    temp_unit: str = "F"
    distance_unit: str = "mi"
    pressure_unit: str = "psi"
    _formatter: OutputFormatter | None = dataclasses.field(default=None, repr=False)

    @property
    def formatter(self) -> OutputFormatter:
        if self._formatter is None:
            from tescmd.output.rich_output import (
                DisplayUnits,
                DistanceUnit,
                PressureUnit,
                TempUnit,
            )

            force = "quiet" if self.quiet else self.output_format
            units = DisplayUnits(
                temp=TempUnit(self.temp_unit),
                distance=DistanceUnit(self.distance_unit),
                pressure=PressureUnit(self.pressure_unit),
            )
            self._formatter = OutputFormatter(force_format=force, units=units)
        return self._formatter


# ---------------------------------------------------------------------------
# Load .env into os.environ before Click resolves any envvar= options.
# This ensures TESLA_VIN, TESCMD_MCP_CLIENT_ID, etc. from .env files
# are visible to Click's envvar resolution.
# ---------------------------------------------------------------------------
load_dotenv(override=False)

# ---------------------------------------------------------------------------
# Root Click group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--vin", default=None, envvar="TESLA_VIN", help="Vehicle VIN")
@click.option("--profile", default="default", help="Config profile name")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["rich", "json", "quiet"]),
    default=None,
    help="Output format (default: auto-detect)",
)
@click.option("--quiet", is_flag=True, default=False, help="Suppress normal output")
@click.option(
    "--region",
    type=click.Choice(["na", "eu", "cn"]),
    default=None,
    help="Tesla API region",
)
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose logging")
@click.option(
    "--no-cache", "--fresh", "no_cache", is_flag=True, default=False, help="Bypass response cache"
)
@click.option(
    "--wake", is_flag=True, default=False, help="Auto-wake vehicle without confirmation (billable)"
)
@click.option(
    "--units",
    type=click.Choice(["us", "metric"]),
    default=None,
    help="Display units preset (us: °F/mi/psi, metric: °C/km/bar)",
)
@click.pass_context
def cli(
    ctx: click.Context,
    vin: str | None,
    profile: str,
    output_format: str | None,
    quiet: bool,
    region: str | None,
    verbose: bool,
    no_cache: bool,
    wake: bool,
    units: str | None,
) -> None:
    """Query and control Tesla vehicles via the Fleet API."""
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(name)s %(levelname)s: %(message)s",
        )

    # Resolve display units: --units flag > env vars > defaults
    from tescmd.models.config import AppSettings

    settings = AppSettings()
    if units == "metric":
        temp_unit, distance_unit, pressure_unit = "C", "km", "bar"
    elif units == "us":
        temp_unit, distance_unit, pressure_unit = "F", "mi", "psi"
    else:
        temp_unit = settings.temp_unit
        distance_unit = settings.distance_unit
        pressure_unit = settings.pressure_unit

    ctx.ensure_object(dict)
    ctx.obj = AppContext(
        vin=vin,
        profile=profile,
        output_format=output_format,
        quiet=quiet,
        region=region,
        verbose=verbose,
        no_cache=no_cache,
        auto_wake=wake,
        temp_unit=temp_unit,
        distance_unit=distance_unit,
        pressure_unit=pressure_unit,
    )


# ---------------------------------------------------------------------------
# Register subcommand groups (lazy imports keep startup fast)
# ---------------------------------------------------------------------------


def _register_commands() -> None:
    """Import and attach all subcommand groups to the root CLI."""
    from tescmd.cli.auth import auth_group
    from tescmd.cli.billing import billing_group
    from tescmd.cli.cache import cache_group
    from tescmd.cli.charge import charge_group
    from tescmd.cli.climate import climate_group
    from tescmd.cli.energy import energy_group
    from tescmd.cli.key import key_group
    from tescmd.cli.mcp_cmd import mcp_group
    from tescmd.cli.media import media_group
    from tescmd.cli.nav import nav_group
    from tescmd.cli.openclaw import openclaw_group
    from tescmd.cli.partner import partner_group
    from tescmd.cli.raw import raw_group
    from tescmd.cli.security import security_group
    from tescmd.cli.serve import serve_cmd
    from tescmd.cli.setup import setup_cmd
    from tescmd.cli.sharing import sharing_group
    from tescmd.cli.software import software_group
    from tescmd.cli.status import status_cmd
    from tescmd.cli.trunk import trunk_group
    from tescmd.cli.user import user_group
    from tescmd.cli.vehicle import vehicle_group

    cli.add_command(auth_group)
    cli.add_command(cache_group)
    cli.add_command(charge_group)
    cli.add_command(billing_group)
    cli.add_command(climate_group)
    cli.add_command(energy_group)
    cli.add_command(key_group)
    cli.add_command(mcp_group)
    cli.add_command(media_group)
    cli.add_command(nav_group)
    cli.add_command(openclaw_group)
    cli.add_command(partner_group)
    cli.add_command(raw_group)
    cli.add_command(security_group)
    cli.add_command(serve_cmd)
    cli.add_command(setup_cmd)
    cli.add_command(sharing_group)
    cli.add_command(status_cmd)
    cli.add_command(software_group)
    cli.add_command(trunk_group)
    cli.add_command(user_group)
    cli.add_command(vehicle_group)


_register_commands()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Parse arguments and dispatch to the appropriate command handler."""
    try:
        cli(args=argv, standalone_mode=False)
    except click.exceptions.Exit as exc:
        raise SystemExit(exc.exit_code) from None
    except click.exceptions.Abort:
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except SystemExit:
        raise
    except Exception as exc:
        # Reconstruct command name for error messages
        app_ctx = _extract_app_ctx()
        formatter = app_ctx.formatter if app_ctx else OutputFormatter()
        cmd_name = _get_command_name()

        if _handle_known_error(exc, app_ctx, formatter, cmd_name):
            raise SystemExit(1) from exc

        exc_type = type(exc).__name__
        exc_msg = str(exc)
        # Never show an empty error — always include the exception class.
        message = exc_msg if exc_msg else f"Unexpected {exc_type}"
        formatter.output_error(
            code=exc_type,
            message=message,
            command=cmd_name,
        )
        if not exc_msg and formatter.format != "json":
            # The message was empty — nudge toward --verbose for the traceback.
            formatter.rich.info("[dim]Run with --verbose to see the full traceback.[/dim]")
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# Helpers for error handling
# ---------------------------------------------------------------------------


def _extract_app_ctx() -> AppContext | None:
    """Try to extract AppContext from the current Click context."""
    ctx = click.get_current_context(silent=True)
    while ctx is not None:
        if isinstance(ctx.obj, AppContext):
            return ctx.obj
        ctx = ctx.parent
    return None


def _get_command_name() -> str:
    """Reconstruct a dotted command name from the Click context chain."""
    ctx = click.get_current_context(silent=True)
    parts: list[str] = []
    while ctx is not None:
        if ctx.info_name and ctx.info_name != "cli":
            parts.append(ctx.info_name)
        ctx = ctx.parent
    return ".".join(reversed(parts)) or "unknown"


def _handle_known_error(
    exc: Exception,
    app_ctx: AppContext | None,
    formatter: OutputFormatter,
    cmd_name: str,
) -> bool:
    """Handle well-known errors with friendly output.

    Returns ``True`` if the error was handled and the caller should exit.
    """
    if isinstance(exc, MissingScopesError):
        _handle_missing_scopes(exc, formatter, cmd_name)
        return True
    if isinstance(exc, AuthError):
        _handle_auth_error(exc, formatter, cmd_name)
        return True
    if isinstance(exc, VehicleAsleepError):
        _handle_vehicle_asleep(exc, formatter, cmd_name)
        return True
    if isinstance(exc, RegistrationRequiredError):
        _handle_registration_required(exc, app_ctx, formatter, cmd_name)
        return True
    if isinstance(exc, TierError):
        _handle_tier_error(exc, formatter, cmd_name)
        return True
    if isinstance(exc, KeyNotEnrolledError):
        _handle_key_not_enrolled(exc, formatter, cmd_name)
        return True
    if isinstance(exc, SessionError):
        _handle_session_error(exc, formatter, cmd_name)
        return True
    if isinstance(exc, TunnelError):
        _handle_tunnel_error(exc, formatter, cmd_name)
        return True

    # Keyring failures (e.g. headless Linux with no keyring daemon)
    try:
        from keyring.errors import KeyringError

        if isinstance(exc, KeyringError):
            _handle_keyring_error(exc, formatter, cmd_name)
            return True
    except ImportError:
        pass

    return False


def _handle_missing_scopes(
    exc: MissingScopesError,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly error when the token lacks required OAuth scopes."""
    message = "Your OAuth token is missing required scopes for this command."

    if formatter.format == "json":
        formatter.output_error(
            code="missing_scopes",
            message=(
                f"{message} Re-login with 'tescmd auth login'. If the error persists, "
                "check your Tesla Developer Portal app and ensure all required "
                "scopes are enabled. Note: 'tescmd auth status' shows requested scopes, "
                "not what Tesla granted — Tesla silently drops scopes your app "
                "isn't configured for."
            ),
            command=cmd_name,
        )
        return

    formatter.rich.error(message)
    formatter.rich.info("")
    formatter.rich.info("Next steps:")
    formatter.rich.info("  1. Re-login to refresh your token:")
    formatter.rich.info("     [cyan]tescmd auth login[/cyan]")
    formatter.rich.info("")
    formatter.rich.info("  2. If the error persists, check your Tesla Developer Portal app")
    formatter.rich.info("     at [cyan]https://developer.tesla.com[/cyan] and ensure all")
    formatter.rich.info("     required scopes are enabled (user_data, energy_device_data, etc.).")
    formatter.rich.info("")
    formatter.rich.info(
        "[dim]Note: 'tescmd auth status' shows scopes that were requested, not necessarily"
        " what Tesla granted. Tesla silently drops scopes your Developer Portal app"
        " isn't configured for.[/dim]"
    )


def _handle_auth_error(
    exc: AuthError,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly authentication error with next steps.

    Uses the exception's message when available, falling back to a generic
    description.
    """
    message = str(exc) or "Authentication failed. Your access token may be expired or invalid."
    hint = "Run 'tescmd auth login' to re-authenticate."

    if formatter.format == "json":
        formatter.output_error(
            code="auth_failed",
            message=f"{message} {hint}",
            command=cmd_name,
        )
        return

    formatter.rich.error(message)
    formatter.rich.info("")
    formatter.rich.info("Next steps:")
    formatter.rich.info("  [cyan]tescmd auth login[/cyan]")
    formatter.rich.info("")
    formatter.rich.info(
        "[dim]If a refresh token is available and TESLA_CLIENT_ID is set,"
        " tescmd will auto-refresh on the next request.[/dim]"
    )


def _handle_vehicle_asleep(
    exc: VehicleAsleepError,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly message when the vehicle is asleep.

    Uses the exception's message directly — it already distinguishes
    between user-cancelled wake and actual API failure.
    """
    message = str(exc)
    hint = "Use --wake to send a billable wake via the API, or wake from the Tesla app for free."

    if formatter.format == "json":
        formatter.output_error(
            code="vehicle_asleep",
            message=f"{message} {hint}",
            command=cmd_name,
        )
        return

    formatter.rich.info(f"[yellow]{message}[/yellow]")
    formatter.rich.info("")
    formatter.rich.info("Next steps:")
    formatter.rich.info("  [cyan]tescmd vehicle wake --wait[/cyan]  (billable)")
    formatter.rich.info("  Or wake from the Tesla app (free), then retry.")


def _handle_registration_required(
    exc: RegistrationRequiredError,
    app_ctx: AppContext | None,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Try auto-registration, or show friendly instructions."""
    from tescmd.auth.oauth import register_partner_account
    from tescmd.models.config import AppSettings

    settings = AppSettings()
    region = (app_ctx.region if app_ctx else None) or settings.region

    message = str(exc) or "Your application is not registered with the Fleet API."
    if formatter.format == "json":
        formatter.output_error(
            code="registration_required",
            message=f"{message} Run 'tescmd auth register' to fix this.",
            command=cmd_name,
        )
        return

    can_register = settings.client_id and settings.client_secret
    domain = settings.domain

    # Prompt for domain if we have credentials but no domain
    if can_register and not domain:
        from tescmd.cli.auth import _prompt_for_domain

        domain = _prompt_for_domain(formatter)

    # Try auto-fix if we have everything
    if can_register and domain:
        assert settings.client_id is not None
        assert settings.client_secret is not None
        formatter.rich.info(
            "[yellow]Your app is not yet registered with the Fleet API."
            " Registering now...[/yellow]"
        )
        try:
            _result, _scopes = run_async(
                register_partner_account(
                    client_id=settings.client_id,
                    client_secret=settings.client_secret,
                    domain=domain,
                    region=region,
                )
            )
            formatter.rich.info("[green]Registration successful![/green]")
            formatter.rich.info("")
            formatter.rich.info("Please re-run your command:")
            formatter.rich.info(f"  [cyan]tescmd {cmd_name.replace('.', ' ')}[/cyan]")
            return
        except Exception as reg_exc:
            formatter.rich.info(f"[red]Registration failed:[/red] {reg_exc}")

    formatter.rich.info("")
    formatter.rich.info(
        "[yellow]Your application is not registered with the"
        " Tesla Fleet API for this region.[/yellow]"
    )
    formatter.rich.info("")
    formatter.rich.info("To fix this, run:")
    formatter.rich.info("  [cyan]tescmd auth register[/cyan]")
    formatter.rich.info("")
    formatter.rich.info(
        "[dim]This is a one-time step after creating your developer application.[/dim]"
    )


def _handle_tier_error(
    exc: TierError,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly tier-mismatch error with upgrade guidance."""
    message = str(exc) or "This command requires 'full' tier setup."

    if formatter.format == "json":
        formatter.output_error(
            code="tier_readonly",
            message=message,
            command=cmd_name,
        )
        return

    formatter.rich.error(message)
    formatter.rich.info("")
    formatter.rich.info("Your setup tier is [yellow]readonly[/yellow].")
    formatter.rich.info(
        "Vehicle commands (lock, charge, climate, etc.) require [cyan]full[/cyan] tier."
    )
    formatter.rich.info("")
    formatter.rich.info("To upgrade:")
    formatter.rich.info("  [cyan]tescmd setup[/cyan]")


def _handle_key_not_enrolled(
    exc: KeyNotEnrolledError,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly key-not-enrolled error with enrollment steps."""
    from tescmd.models.config import AppSettings

    message = str(exc) or "Your key is not enrolled on this vehicle."
    settings = AppSettings()
    domain = settings.domain

    if formatter.format == "json":
        if domain:
            message += f" Enroll at https://tesla.com/_ak/{domain}"
        formatter.output_error(
            code="key_not_enrolled",
            message=message,
            command=cmd_name,
        )
        return

    formatter.rich.error(message)
    formatter.rich.info("")
    if domain:
        enroll_url = f"https://tesla.com/_ak/{domain}"
        formatter.rich.info("To enroll your key:")
        formatter.rich.info(f"  1. Open [link={enroll_url}]{enroll_url}[/link] on your phone")
        formatter.rich.info("  2. Tap [bold]Finish Setup[/bold] on the web page")
        formatter.rich.info(
            "  3. Approve the [bold]Add Virtual Key[/bold] prompt in the Tesla app"
        )
        formatter.rich.info("")
        formatter.rich.info(
            "Or run [cyan]tescmd key enroll[/cyan] to see the full enrollment guide."
        )
    else:
        formatter.rich.info("To enroll your key:")
        formatter.rich.info("  [cyan]tescmd key enroll[/cyan]")
        formatter.rich.info("")
        formatter.rich.info("[dim]Set TESLA_DOMAIN first if not already configured.[/dim]")


def _handle_session_error(
    exc: SessionError,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly session handshake error with recovery steps."""
    message = str(exc) or "Session handshake with the vehicle failed."

    if formatter.format == "json":
        formatter.output_error(
            code="session_error",
            message=message,
            command=cmd_name,
        )
        return

    formatter.rich.error(message)
    formatter.rich.info("")
    formatter.rich.info("Possible causes:")
    formatter.rich.info("  - Vehicle is temporarily unreachable or asleep")
    formatter.rich.info("  - Session expired — retry once and a fresh handshake will occur")
    formatter.rich.info(
        "  - Local key pair is corrupted or was re-generated without re-enrollment"
    )
    formatter.rich.info("")
    formatter.rich.info("Try:")
    formatter.rich.info("  1. Re-run the command (sessions auto-refresh)")
    formatter.rich.info("  2. Use [cyan]--verbose[/cyan] to see fault codes and signing details")
    formatter.rich.info("  3. If repeated failures, re-enroll:")
    formatter.rich.info(
        "     [cyan]tescmd key generate --force && tescmd key deploy && tescmd key enroll[/cyan]"
    )


def _handle_keyring_error(
    exc: Exception,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly error when the OS keyring is unavailable."""
    message = f"OS keyring error: {exc}"

    if formatter.format == "json":
        formatter.output_error(
            code="keyring_error",
            message=(
                f"{message} Set TESLA_TOKEN_FILE to store tokens in a file "
                "instead of the OS keyring."
            ),
            command=cmd_name,
        )
        return

    formatter.rich.error(message)
    formatter.rich.info("")
    formatter.rich.info("The OS keyring (macOS Keychain, GNOME Keyring, etc.) is unavailable.")
    formatter.rich.info("This is common in Docker, headless Linux, and CI environments.")
    formatter.rich.info("")
    formatter.rich.info("To fix this, set a file-based token path:")
    formatter.rich.info("  [cyan]export TESLA_TOKEN_FILE=~/.config/tescmd/tokens.json[/cyan]")
    formatter.rich.info("")
    formatter.rich.info(
        "[dim]Tokens will be stored in plaintext with restricted file permissions.[/dim]"
    )


def _handle_tunnel_error(
    exc: TunnelError,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Show a friendly error for tunnel-related failures.

    Only shows install guidance when no provider is found on PATH.
    TailscaleError means Tailscale IS installed but hit an operational
    error — install guidance would be confusing.
    """
    message = str(exc) or "No tunnel provider available for telemetry streaming."

    if formatter.format == "json":
        formatter.output_error(
            code="tunnel_error",
            message=message,
            command=cmd_name,
        )
        return

    formatter.rich.error(message)

    # Only show install guidance when no provider was found at all.
    if "No tunnel provider" not in message:
        return

    formatter.rich.info("")
    formatter.rich.info("Telemetry streaming requires Tailscale Funnel:")
    formatter.rich.info("")
    formatter.rich.info("  1. Install Tailscale: [cyan]https://tailscale.com/download[/cyan]")
    formatter.rich.info("  2. Authenticate: [cyan]tailscale up[/cyan]")
    formatter.rich.info(
        "  3. Enable Funnel in your tailnet ACL:"
        " [cyan]https://login.tailscale.com/admin/acls[/cyan]"
    )
    formatter.rich.info("")
    formatter.rich.info("Telemetry deps are included with tescmd.")
