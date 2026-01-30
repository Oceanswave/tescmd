"""CLI entry-point: Click command group and dispatch."""

from __future__ import annotations

import dataclasses

import click

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import AuthError, RegistrationRequiredError, VehicleAsleepError
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
    _formatter: OutputFormatter | None = dataclasses.field(default=None, repr=False)

    @property
    def formatter(self) -> OutputFormatter:
        if self._formatter is None:
            force = "quiet" if self.quiet else self.output_format
            self._formatter = OutputFormatter(force_format=force)
        return self._formatter


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
) -> None:
    """Query and control Tesla vehicles via the Fleet API."""
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
    )


# ---------------------------------------------------------------------------
# Register subcommand groups (lazy imports keep startup fast)
# ---------------------------------------------------------------------------


def _register_commands() -> None:
    """Import and attach all subcommand groups to the root CLI."""
    from tescmd.cli.auth import auth_group
    from tescmd.cli.cache import cache_group
    from tescmd.cli.charge import charge_group
    from tescmd.cli.climate import climate_group
    from tescmd.cli.energy import energy_group
    from tescmd.cli.key import key_group
    from tescmd.cli.media import media_group
    from tescmd.cli.nav import nav_group
    from tescmd.cli.raw import raw_group
    from tescmd.cli.security import security_group
    from tescmd.cli.setup import setup_cmd
    from tescmd.cli.sharing import sharing_group
    from tescmd.cli.software import software_group
    from tescmd.cli.trunk import trunk_group
    from tescmd.cli.user import user_group
    from tescmd.cli.vehicle import vehicle_group

    cli.add_command(auth_group)
    cli.add_command(cache_group)
    cli.add_command(charge_group)
    cli.add_command(climate_group)
    cli.add_command(energy_group)
    cli.add_command(key_group)
    cli.add_command(media_group)
    cli.add_command(nav_group)
    cli.add_command(raw_group)
    cli.add_command(security_group)
    cli.add_command(setup_cmd)
    cli.add_command(sharing_group)
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

        formatter.output_error(
            code=type(exc).__name__,
            message=str(exc),
            command=cmd_name,
        )
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
    if isinstance(exc, AuthError):
        _handle_auth_error(exc, formatter, cmd_name)
        return True
    if isinstance(exc, VehicleAsleepError):
        _handle_vehicle_asleep(exc, formatter, cmd_name)
        return True
    if isinstance(exc, RegistrationRequiredError):
        _handle_registration_required(exc, app_ctx, formatter, cmd_name)
        return True
    return False


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
            run_async(
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
