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
@click.option("--site", "site_id", default=None, help="Clear cache for an energy site ID")
@click.option(
    "--scope",
    "scope",
    type=click.Choice(["account", "partner"]),
    default=None,
    help="Clear cache entries for a scope (account or partner)",
)
@global_options
def clear_cmd(app_ctx: AppContext, site_id: str | None, scope: str | None) -> None:
    """Clear cached API responses.

    \b
    Filters (first matching rule wins):
      --vin VIN              Vehicle-specific entries (legacy + generic)
      --site SITE_ID         Energy site entries
      --scope account|partner  Scope-level entries
      (none)                 Clear everything
    """
    formatter = app_ctx.formatter
    cache = get_cache(app_ctx)
    target_vin = app_ctx.vin
    removed = 0
    label = ""

    if target_vin:
        removed += cache.clear(target_vin)
        removed += cache.clear_by_prefix(f"vin_{target_vin}_")
        label = f" for VIN {target_vin}"
    elif site_id:
        removed = cache.clear_by_prefix(f"site_{site_id}_")
        label = f" for site {site_id}"
    elif scope:
        removed = cache.clear_by_prefix(f"{scope}_")
        label = f" for scope '{scope}'"
    else:
        removed = cache.clear()

    if formatter.format == "json":
        formatter.output(
            {"cleared": removed, "vin": target_vin, "site": site_id, "scope": scope},
            command="cache.clear",
        )
    else:
        formatter.rich.info(f"Cleared {removed} cache entries{label}.")


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
