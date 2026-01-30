"""Shared CLI decorator that propagates global options to leaf commands."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext


def global_options(f: Any) -> Any:
    """Add global CLI options to a leaf command.

    Allows ``--vin``, ``--profile``, ``--format``, ``--quiet``, ``--region``,
    and ``--verbose`` to be specified **after** the subcommand name (e.g.
    ``tescmd vehicle info --vin X``).  Command-level values override the
    root-group values stored in :class:`AppContext`.
    """

    @click.option(
        "--wake",
        "local_wake",
        is_flag=True,
        default=False,
        help="Auto-wake vehicle without confirmation (billable)",
    )
    @click.option(
        "--no-cache",
        "--fresh",
        "local_no_cache",
        is_flag=True,
        default=False,
        help="Bypass response cache",
    )
    @click.option(
        "--verbose",
        "local_verbose",
        is_flag=True,
        default=False,
        help="Enable verbose logging",
    )
    @click.option(
        "--region",
        "local_region",
        type=click.Choice(["na", "eu", "cn"]),
        default=None,
        help="Tesla API region",
    )
    @click.option(
        "--quiet",
        "local_quiet",
        is_flag=True,
        default=False,
        help="Suppress normal output",
    )
    @click.option(
        "--format",
        "local_output_format",
        type=click.Choice(["rich", "json", "quiet"]),
        default=None,
        help="Output format (default: auto-detect)",
    )
    @click.option("--profile", "local_profile", default=None, help="Config profile name")
    @click.option("--vin", "local_vin", default=None, help="Vehicle VIN")
    @click.pass_obj
    def wrapper(app_ctx: AppContext, /, **kwargs: Any) -> Any:
        # Pop command-level global-option overrides
        local_vin: str | None = kwargs.pop("local_vin", None)
        local_profile: str | None = kwargs.pop("local_profile", None)
        local_output_format: str | None = kwargs.pop("local_output_format", None)
        local_quiet: bool = kwargs.pop("local_quiet", False)
        local_region: str | None = kwargs.pop("local_region", None)
        local_verbose: bool = kwargs.pop("local_verbose", False)
        local_no_cache: bool = kwargs.pop("local_no_cache", False)
        local_wake: bool = kwargs.pop("local_wake", False)

        # Merge overrides into AppContext (command-level wins)
        if local_vin is not None:
            app_ctx.vin = local_vin
        if local_profile is not None:
            app_ctx.profile = local_profile
        if local_output_format is not None:
            app_ctx.output_format = local_output_format
            app_ctx._formatter = None  # reset cached formatter
        if local_quiet:
            app_ctx.quiet = True
            app_ctx._formatter = None
        if local_region is not None:
            app_ctx.region = local_region
        if local_verbose:
            app_ctx.verbose = True
        if local_no_cache:
            app_ctx.no_cache = True
        if local_wake:
            app_ctx.auto_wake = True

        return f(app_ctx, **kwargs)

    functools.update_wrapper(wrapper, f)
    return wrapper
