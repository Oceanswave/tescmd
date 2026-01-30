"""CLI entry-point: argument parsing and dispatch."""

from __future__ import annotations

import argparse
from typing import NoReturn

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import RegistrationRequiredError
from tescmd.output.formatter import OutputFormatter


def build_parser() -> argparse.ArgumentParser:
    """Build the root argument parser with global flags and subcommands."""
    from tescmd.cli import auth as auth_cli
    from tescmd.cli import vehicle as vehicle_cli

    parser = argparse.ArgumentParser(
        prog="tescmd",
        description="Query and control Tesla vehicles via the Fleet API.",
    )

    # -- global flags --------------------------------------------------------
    parser.add_argument("--vin", default=None, help="Vehicle VIN")
    parser.add_argument("--profile", default="default", help="Config profile name")
    parser.add_argument(
        "--format",
        choices=["rich", "json", "quiet"],
        default=None,
        dest="output_format",
        help="Output format (default: auto-detect)",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress normal output")
    parser.add_argument(
        "--region",
        choices=["na", "eu", "cn"],
        default=None,
        help="Tesla API region",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    # -- subcommands ---------------------------------------------------------
    subparsers = parser.add_subparsers(dest="command")
    auth_cli.register(subparsers)
    vehicle_cli.register(subparsers)

    return parser


def main(argv: list[str] | None = None) -> NoReturn:
    """Parse arguments, create formatter, and dispatch to the command handler."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # No command given → print help
    if not args.command:
        parser.print_help()
        raise SystemExit(0)

    # Sub-command without a func (e.g. `tescmd auth` with no sub-sub-command)
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(0)

    # Build formatter
    force_format: str | None = "quiet" if args.quiet else args.output_format
    formatter = OutputFormatter(force_format=force_format)

    try:
        run_async(args.func(args, formatter))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except SystemExit:
        raise
    except Exception as exc:
        cmd_name: str = args.command
        if hasattr(args, "subcommand") and args.subcommand:
            cmd_name = f"{args.command}.{args.subcommand}"

        # Friendly handling for known error types
        if _handle_known_error(exc, args, formatter, cmd_name):
            raise SystemExit(1) from exc

        formatter.output_error(
            code=type(exc).__name__,
            message=str(exc),
            command=cmd_name,
        )
        raise SystemExit(1) from exc

    raise SystemExit(0)


# ---------------------------------------------------------------------------
# Friendly error handlers
# ---------------------------------------------------------------------------


def _handle_known_error(
    exc: Exception,
    args: argparse.Namespace,
    formatter: OutputFormatter,
    cmd_name: str,
) -> bool:
    """Handle well-known errors with friendly output.

    Returns ``True`` if the error was handled and the caller should exit.
    """
    if isinstance(exc, RegistrationRequiredError):
        _handle_registration_required(exc, args, formatter, cmd_name)
        return True
    return False


def _handle_registration_required(
    exc: RegistrationRequiredError,
    args: argparse.Namespace,
    formatter: OutputFormatter,
    cmd_name: str,
) -> None:
    """Try auto-registration, or show friendly instructions."""
    from tescmd.auth.oauth import register_partner_account
    from tescmd.models.config import AppSettings

    settings = AppSettings()
    region = getattr(args, "region", None) or settings.region

    if formatter.format == "json":
        formatter.output_error(
            code="registration_required",
            message=(
                "Your application is not registered with the Fleet API. "
                "Run 'tescmd auth register' to fix this."
            ),
            command=cmd_name,
        )
        return

    # Try auto-fix if we have the credentials
    if settings.client_id and settings.client_secret:
        formatter.rich.info(
            "[yellow]Your app is not yet registered with the Fleet API."
            " Attempting to register now...[/yellow]"
        )
        try:
            run_async(
                register_partner_account(
                    client_id=settings.client_id,
                    client_secret=settings.client_secret,
                    domain="localhost",
                    region=region,
                )
            )
            formatter.rich.info("[green]Registration successful![/green]")
            formatter.rich.info("")
            formatter.rich.info("Please re-run your command:")
            formatter.rich.info(
                f"  [cyan]tescmd {cmd_name.replace('.', ' ')}[/cyan]"
            )
            return
        except Exception:
            pass  # Fall through to manual instructions

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
        "[dim]This is a one-time step after creating your"
        " developer application.[/dim]"
    )
