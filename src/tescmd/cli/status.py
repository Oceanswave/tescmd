"""CLI command for showing current configuration status."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import click

from tescmd.auth.token_store import TokenStore
from tescmd.cli._client import get_cache
from tescmd.cli._options import global_options
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext


@click.command("status")
@global_options
def status_cmd(app_ctx: AppContext) -> None:
    """Show current configuration, authentication, and cache status."""
    formatter = app_ctx.formatter
    settings = AppSettings()
    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )
    cache = get_cache(app_ctx)
    cache_info = cache.status()

    # Auth info
    has_token = store.has_token
    meta = store.metadata or {}
    expires_at = meta.get("expires_at", 0.0)
    expires_in = max(0, int(expires_at - time.time())) if has_token else 0
    has_refresh = bool(store.refresh_token)

    # Key info
    key_dir = Path(settings.config_dir).expanduser() / "keys"
    key_count = len(list(key_dir.glob("*.pem"))) // 2 if key_dir.is_dir() else 0

    # Mask client ID
    cid = settings.client_id
    client_id_display = (cid[:8] + "\u2026") if cid and len(cid) > 8 else (cid or "not set")

    data = {
        "profile": app_ctx.profile,
        "region": settings.region,
        "vin": settings.vin,
        "setup_tier": settings.setup_tier,
        "domain": settings.domain,
        "client_id": client_id_display,
        "authenticated": has_token,
        "expires_in": expires_in if has_token else None,
        "has_refresh_token": has_refresh,
        "cache_enabled": cache_info["enabled"],
        "cache_ttl": cache_info["default_ttl"],
        "cache_entries": cache_info["total"],
        "cache_fresh": cache_info["fresh"],
        "cache_stale": cache_info["stale"],
        "config_dir": settings.config_dir,
        "cache_dir": settings.cache_dir,
        "key_pairs": key_count,
        "token_backend": store.backend_name,
    }

    if formatter.format == "json":
        formatter.output(data, command="status")
    else:
        # Profile & API
        formatter.rich.info(f"Profile:     {data['profile']}")
        formatter.rich.info(f"Region:      {data['region']}")
        formatter.rich.info(f"VIN:         {data['vin'] or '[dim]not set[/dim]'}")
        formatter.rich.info(f"Setup tier:  {data['setup_tier'] or '[dim]not set[/dim]'}")
        formatter.rich.info(f"Domain:      {data['domain'] or '[dim]not set[/dim]'}")
        formatter.rich.info(f"Client ID:   {data['client_id']}")
        formatter.rich.info("")

        # Auth
        formatter.rich.info(f"Token store: {data['token_backend']}")
        auth_str = "[green]authenticated[/green]" if has_token else "[red]not authenticated[/red]"
        formatter.rich.info(f"Auth:        {auth_str}")
        if has_token:
            formatter.rich.info(f"Expires in:  {expires_in}s")
            refresh_str = "[green]yes[/green]" if has_refresh else "[yellow]no[/yellow]"
            formatter.rich.info(f"Refresh:     {refresh_str}")
        formatter.rich.info("")

        # Cache
        cache_str = "[green]enabled[/green]" if data["cache_enabled"] else "[red]disabled[/red]"
        formatter.rich.info(f"Cache:       {cache_str}")
        formatter.rich.info(f"TTL:         {data['cache_ttl']}s")
        formatter.rich.info(
            f"Entries:     {data['cache_entries']}"
            f" ({data['cache_fresh']} fresh, {data['cache_stale']} stale)"
        )
        formatter.rich.info("")

        # Paths
        formatter.rich.info(f"Config dir:  {data['config_dir']}")
        formatter.rich.info(f"Cache dir:   {data['cache_dir']}")
        key_str = f"{key_dir} ({key_count} key pair{'s' if key_count != 1 else ''})"
        formatter.rich.info(f"Keys:        {key_str}")
