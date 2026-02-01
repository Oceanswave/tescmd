"""CLI commands for energy products (Powerwall, Solar)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import TTL_SLOW, cached_api_call, get_energy_api, invalidate_cache_for_site
from tescmd.cli._options import global_options
from tescmd.models.energy import SiteInfo

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

energy_group = click.Group("energy", help="Energy product commands (Powerwall, Solar)")


@energy_group.command("list")
@global_options
def list_cmd(app_ctx: AppContext) -> None:
    """List energy products (Powerwalls, Solar, etc.)."""
    run_async(_cmd_list(app_ctx))


async def _cmd_list(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        products = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="energy.list",
            fetch=lambda: api.list_products(),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    # Filter to energy products (have energy_site_id)
    energy_products = [p for p in products if "energy_site_id" in p]

    if formatter.format == "json":
        formatter.output(energy_products, command="energy.list")
    else:
        formatter.rich.energy_site_list(energy_products)


@energy_group.command("status")
@click.argument("site_id", type=int)
@global_options
def status_cmd(app_ctx: AppContext, site_id: int) -> None:
    """Show energy site info."""
    run_async(_cmd_status(app_ctx, site_id))


async def _cmd_status(app_ctx: AppContext, site_id: int) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="site",
            identifier=str(site_id),
            endpoint="energy.status",
            fetch=lambda: api.site_info(site_id),
            ttl=TTL_SLOW,
            model_class=SiteInfo,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="energy.status")
    else:
        formatter.rich.energy_site_info(data)


@energy_group.command("live")
@click.argument("site_id", type=int)
@global_options
def live_cmd(app_ctx: AppContext, site_id: int) -> None:
    """Show real-time power flow."""
    run_async(_cmd_live(app_ctx, site_id))


async def _cmd_live(app_ctx: AppContext, site_id: int) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        data = await api.live_status(site_id)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="energy.live")
    else:
        formatter.rich.energy_live_status(data)


@energy_group.command("backup")
@click.argument("site_id", type=int)
@click.argument("percent", type=click.IntRange(0, 100))
@global_options
def backup_cmd(app_ctx: AppContext, site_id: int, percent: int) -> None:
    """Set backup reserve percentage."""
    run_async(_cmd_backup(app_ctx, site_id, percent))


async def _cmd_backup(app_ctx: AppContext, site_id: int, percent: int) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        result = await api.set_backup_reserve(site_id, percent=percent)
    finally:
        await client.close()

    invalidate_cache_for_site(app_ctx, site_id)

    if formatter.format == "json":
        formatter.output(result, command="energy.backup")
    else:
        formatter.rich.info(f"Backup reserve set to {percent}%")


@energy_group.command("mode")
@click.argument("site_id", type=int)
@click.argument(
    "mode",
    type=click.Choice(["self_consumption", "backup", "autonomous"]),
)
@global_options
def mode_cmd(app_ctx: AppContext, site_id: int, mode: str) -> None:
    """Set operation mode (self_consumption, backup, autonomous)."""
    run_async(_cmd_mode(app_ctx, site_id, mode))


async def _cmd_mode(app_ctx: AppContext, site_id: int, mode: str) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        result = await api.set_operation_mode(site_id, mode=mode)
    finally:
        await client.close()

    invalidate_cache_for_site(app_ctx, site_id)

    if formatter.format == "json":
        formatter.output(result, command="energy.mode")
    else:
        formatter.rich.info(f"Operation mode set to {mode}")


@energy_group.command("storm")
@click.argument("site_id", type=int)
@click.option("--on/--off", default=True, help="Enable or disable storm watch")
@global_options
def storm_cmd(app_ctx: AppContext, site_id: int, on: bool) -> None:
    """Enable or disable storm watch."""
    run_async(_cmd_storm(app_ctx, site_id, on))


async def _cmd_storm(app_ctx: AppContext, site_id: int, on: bool) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        result = await api.set_storm_mode(site_id, enabled=on)
    finally:
        await client.close()

    invalidate_cache_for_site(app_ctx, site_id)

    if formatter.format == "json":
        formatter.output(result, command="energy.storm")
    else:
        label = "enabled" if on else "disabled"
        formatter.rich.info(f"Storm watch {label}")


@energy_group.command("tou")
@click.argument("site_id", type=int)
@click.argument("settings_json")
@global_options
def tou_cmd(app_ctx: AppContext, site_id: int, settings_json: str) -> None:
    """Set time-of-use schedule (SETTINGS_JSON is a JSON string)."""
    import json

    settings = json.loads(settings_json)
    run_async(_cmd_tou(app_ctx, site_id, settings))


async def _cmd_tou(app_ctx: AppContext, site_id: int, settings: dict[str, object]) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        result = await api.time_of_use_settings(site_id, settings=settings)
    finally:
        await client.close()

    invalidate_cache_for_site(app_ctx, site_id)

    if formatter.format == "json":
        formatter.output(result, command="energy.tou")
    else:
        formatter.rich.info("Time-of-use settings updated")


@energy_group.command("history")
@click.argument("site_id", type=int)
@global_options
def history_cmd(app_ctx: AppContext, site_id: int) -> None:
    """Show charging history for an energy site."""
    run_async(_cmd_history(app_ctx, site_id))


async def _cmd_history(app_ctx: AppContext, site_id: int) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        data = await api.charging_history(site_id)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="energy.history")
    else:
        if data.time_series:
            formatter.rich.info(f"Charging history: {len(data.time_series)} entries")
        else:
            formatter.rich.info("No charging history available.")


@energy_group.command("off-grid")
@click.argument("site_id", type=int)
@click.argument("reserve", type=click.IntRange(0, 100))
@global_options
def off_grid_cmd(app_ctx: AppContext, site_id: int, reserve: int) -> None:
    """Set off-grid EV charging reserve percentage."""
    run_async(_cmd_off_grid(app_ctx, site_id, reserve))


async def _cmd_off_grid(app_ctx: AppContext, site_id: int, reserve: int) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        result = await api.off_grid_vehicle_charging_reserve(site_id, reserve=reserve)
    finally:
        await client.close()

    invalidate_cache_for_site(app_ctx, site_id)

    if formatter.format == "json":
        formatter.output(result, command="energy.off-grid")
    else:
        formatter.rich.info(f"Off-grid EV charging reserve set to {reserve}%")


@energy_group.command("grid-config")
@click.argument("site_id", type=int)
@click.argument("config_json")
@global_options
def grid_config_cmd(app_ctx: AppContext, site_id: int, config_json: str) -> None:
    """Set grid import/export config (CONFIG_JSON is a JSON string)."""
    import json

    config = json.loads(config_json)
    run_async(_cmd_grid_config(app_ctx, site_id, config))


async def _cmd_grid_config(app_ctx: AppContext, site_id: int, config: dict[str, object]) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        result = await api.grid_import_export(site_id, config=config)
    finally:
        await client.close()

    invalidate_cache_for_site(app_ctx, site_id)

    if formatter.format == "json":
        formatter.output(result, command="energy.grid-config")
    else:
        formatter.rich.info("Grid import/export config updated")


@energy_group.command("telemetry")
@click.argument("site_id", type=int)
@click.option(
    "--kind", type=click.Choice(["charge", "power"]), default="charge", help="Telemetry data type"
)
@click.option("--start-date", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--end-date", default=None, help="End date (YYYY-MM-DD)")
@click.option("--time-zone", default=None, help="Time zone (e.g. America/Los_Angeles)")
@global_options
def telemetry_cmd(
    app_ctx: AppContext,
    site_id: int,
    kind: str,
    start_date: str | None,
    end_date: str | None,
    time_zone: str | None,
) -> None:
    """Show telemetry history for an energy site (wall connector)."""
    run_async(_cmd_telemetry(app_ctx, site_id, kind, start_date, end_date, time_zone))


async def _cmd_telemetry(
    app_ctx: AppContext,
    site_id: int,
    kind: str,
    start_date: str | None,
    end_date: str | None,
    time_zone: str | None,
) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        data = await api.telemetry_history(
            site_id,
            kind=kind,
            start_date=start_date,
            end_date=end_date,
            time_zone=time_zone,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="energy.telemetry")
    else:
        if data.time_series:
            formatter.rich.info(f"Telemetry history: {len(data.time_series)} entries")
        else:
            formatter.rich.info("No telemetry history available.")


@energy_group.command("calendar")
@click.argument("site_id", type=int)
@click.option(
    "--kind", type=click.Choice(["energy", "backup"]), default="energy", help="History type"
)
@click.option("--period", type=click.Choice(["day", "week", "month", "year"]), default="day")
@click.option("--start-date", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--end-date", default=None, help="End date (YYYY-MM-DD)")
@global_options
def calendar_cmd(
    app_ctx: AppContext,
    site_id: int,
    kind: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
) -> None:
    """Show calendar-based history for an energy site."""
    run_async(_cmd_calendar(app_ctx, site_id, kind, period, start_date, end_date))


async def _cmd_calendar(
    app_ctx: AppContext,
    site_id: int,
    kind: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
) -> None:
    formatter = app_ctx.formatter
    client, api = get_energy_api(app_ctx)
    try:
        data = await api.calendar_history(
            site_id,
            kind=kind,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="energy.calendar")
    else:
        if data.time_series:
            formatter.rich.info(f"Calendar history: {len(data.time_series)} entries")
        else:
            formatter.rich.info("No calendar history available.")
