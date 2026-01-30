"""CLI commands for cache management."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd.cli._client import get_cache
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

cache_group = click.Group("cache", help="Response cache management")


@cache_group.command("clear")
@global_options
def clear_cmd(app_ctx: AppContext) -> None:
    """Clear cached API responses.

    If --vin is provided (global option), clears only that vehicle's cache.
    Otherwise clears all cached entries.
    """
    formatter = app_ctx.formatter
    cache = get_cache(app_ctx)
    target_vin = app_ctx.vin
    removed = cache.clear(target_vin)

    if formatter.format == "json":
        formatter.output(
            {"cleared": removed, "vin": target_vin},
            command="cache.clear",
        )
    else:
        if target_vin:
            formatter.rich.info(f"Cleared {removed} cache entries for VIN {target_vin}.")
        else:
            formatter.rich.info(f"Cleared {removed} cache entries.")


@cache_group.command("status")
@global_options
def status_cmd(app_ctx: AppContext) -> None:
    """Show cache statistics."""
    formatter = app_ctx.formatter
    cache = get_cache(app_ctx)
    info = cache.status()

    if formatter.format == "json":
        formatter.output(info, command="cache.status")
    else:
        enabled_str = "[green]enabled[/green]" if info["enabled"] else "[red]disabled[/red]"
        formatter.rich.info(f"Cache:       {enabled_str}")
        formatter.rich.info(f"Directory:   {info['cache_dir']}")
        formatter.rich.info(f"Default TTL: {info['default_ttl']}s")
        formatter.rich.info(
            f"Entries:     {info['total']} ({info['fresh']} fresh, {info['stale']} stale)"
        )
        disk_kb = info["disk_bytes"] / 1024
        formatter.rich.info(f"Disk usage:  {disk_kb:.1f} KB")
