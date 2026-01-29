"""CLI entry-point: argument parsing and dispatch."""

from __future__ import annotations

import argparse
from typing import NoReturn

from tescmd._internal.async_utils import run_async
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
        formatter.output_error(
            code=type(exc).__name__,
            message=str(exc),
            command=cmd_name,
        )
        raise SystemExit(1) from exc

    raise SystemExit(0)
