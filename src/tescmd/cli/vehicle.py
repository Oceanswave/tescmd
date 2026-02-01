"""CLI commands for vehicle operations (list, info, data, location, wake)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import TunnelError, VehicleAsleepError
from tescmd.cli._client import (
    TTL_DEFAULT,
    TTL_FAST,
    TTL_SLOW,
    TTL_STATIC,
    cached_api_call,
    cached_vehicle_data,
    execute_command,
    get_vehicle_api,
    require_vin,
)
from tescmd.cli._options import global_options

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from tescmd.cli.main import AppContext
    from tescmd.output.formatter import OutputFormatter


# ---------------------------------------------------------------------------
# Command group
# ---------------------------------------------------------------------------

vehicle_group = click.Group("vehicle", help="Vehicle commands")

telemetry_group = click.Group("telemetry", help="Fleet telemetry configuration and errors")
vehicle_group.add_command(telemetry_group)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@vehicle_group.command("list")
@global_options
def list_cmd(app_ctx: AppContext) -> None:
    """List all vehicles on the account."""
    run_async(_cmd_list(app_ctx))


async def _cmd_list(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_vehicle_api(app_ctx)
    try:
        vehicles = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="vehicle.list",
            fetch=lambda: api.list_vehicles(),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vehicles, command="vehicle.list")
    else:
        formatter.rich.vehicle_list(vehicles)


@vehicle_group.command("get")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def get_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Fetch basic vehicle info (lightweight, no wake required)."""
    run_async(_cmd_get(app_ctx, vin_positional))


async def _cmd_get(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        vehicle = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.get",
            fetch=lambda: api.get_vehicle(vin),
            ttl=TTL_DEFAULT,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vehicle, command="vehicle.get")
    else:
        state = vehicle.get("state") if isinstance(vehicle, dict) else vehicle.state
        style = "green" if state == "online" else "yellow"
        if isinstance(vehicle, dict):
            name = vehicle.get("display_name") or vehicle.get("vin") or "Unknown"
            v_vin = vehicle.get("vin", "")
        else:
            name = vehicle.display_name or vehicle.vin or "Unknown"
            v_vin = vehicle.vin
        formatter.rich.info(f"{name}  [{style}]{state}[/{style}]  VIN: {v_vin}")


@vehicle_group.command("info")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def info_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show all vehicle data."""
    run_async(_cmd_info(app_ctx, vin_positional))


async def _cmd_info(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        vdata = await cached_vehicle_data(app_ctx, api, vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vdata, command="vehicle.info")
    else:
        formatter.rich.vehicle_data(vdata)


@vehicle_group.command("data")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--endpoints", default=None, help="Comma-separated endpoint filter")
@global_options
def data_cmd(app_ctx: AppContext, vin_positional: str | None, endpoints: str | None) -> None:
    """Fetch vehicle data filtered by endpoint."""
    run_async(_cmd_data(app_ctx, vin_positional, endpoints))


async def _cmd_data(
    app_ctx: AppContext, vin_positional: str | None, endpoints: str | None
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    endpoint_list: list[str] | None = None
    if endpoints:
        endpoint_list = [e.strip() for e in endpoints.split(",")]

    client, api = get_vehicle_api(app_ctx)
    try:
        vdata = await cached_vehicle_data(app_ctx, api, vin, endpoints=endpoint_list)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vdata, command="vehicle.data")
    else:
        formatter.rich.vehicle_data(vdata)


@vehicle_group.command("location")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def location_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show the vehicle's current location."""
    run_async(_cmd_location(app_ctx, vin_positional))


async def _cmd_location(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        vdata = await cached_vehicle_data(app_ctx, api, vin, endpoints=["drive_state"])
    finally:
        await client.close()

    if formatter.format == "json":
        ds = vdata.drive_state
        formatter.output(
            ds.model_dump(exclude_none=True) if ds else {},
            command="vehicle.location",
        )
    else:
        if vdata.drive_state:
            formatter.rich.location(vdata.drive_state)
        else:
            formatter.rich.info("No drive state data available.")
            if vdata.state == "online":
                formatter.rich.info(
                    "[dim]Location requires a vehicle command key."
                    " Run [cyan]tescmd setup[/cyan] and choose"
                    " full control to enable location access.[/dim]"
                )
            else:
                formatter.rich.info(
                    "[dim]The vehicle may be asleep."
                    " Try [cyan]tescmd vehicle wake[/cyan] first.[/dim]"
                )


@vehicle_group.command("wake")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--wait", is_flag=True, help="Wait for vehicle to come online")
@click.option("--timeout", type=int, default=30, help="Timeout in seconds when using --wait")
@global_options
def wake_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    wait: bool,
    timeout: int,
) -> None:
    """Wake up the vehicle."""
    run_async(_cmd_wake(app_ctx, vin_positional, wait, timeout))


async def _cmd_wake(
    app_ctx: AppContext,
    vin_positional: str | None,
    wait: bool,
    timeout: int,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        vehicle = await api.wake(vin)

        if wait and vehicle.state != "online":
            elapsed = 0
            while elapsed < timeout and vehicle.state != "online":
                await asyncio.sleep(2)
                elapsed += 2
                with contextlib.suppress(VehicleAsleepError):
                    vehicle = await api.wake(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vehicle, command="vehicle.wake")
    else:
        state = vehicle.state
        style = "green" if state == "online" else "yellow"
        formatter.rich.info(f"Vehicle state: [{style}]{state}[/{style}]")


# ---------------------------------------------------------------------------
# Vehicle extras
# ---------------------------------------------------------------------------


@vehicle_group.command("rename")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("name")
@global_options
def rename_cmd(app_ctx: AppContext, vin_positional: str | None, name: str) -> None:
    """Rename the vehicle."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "set_vehicle_name",
            "vehicle.rename",
            body={"vehicle_name": name},
        )
    )


@vehicle_group.command("mobile-access")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def mobile_access_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Check if mobile access is enabled."""
    run_async(_cmd_mobile_access(app_ctx, vin_positional))


async def _cmd_mobile_access(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        result = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.mobile-access",
            fetch=lambda: api.mobile_enabled(vin),
            ttl=TTL_DEFAULT,
        )
    finally:
        await client.close()

    # Result is bool on miss, {"_value": bool} on hit
    enabled = result.get("_value") if isinstance(result, dict) else result
    if formatter.format == "json":
        formatter.output({"mobile_enabled": enabled}, command="vehicle.mobile-access")
    else:
        label = "[green]enabled[/green]" if enabled else "[red]disabled[/red]"
        formatter.rich.info(f"Mobile access: {label}")


@vehicle_group.command("nearby-chargers")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def nearby_chargers_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show nearby Superchargers and destination chargers."""
    run_async(_cmd_nearby_chargers(app_ctx, vin_positional))


async def _cmd_nearby_chargers(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.nearby-chargers",
            fetch=lambda: api.nearby_charging_sites(vin),
            ttl=TTL_FAST,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.nearby-chargers")
    else:
        formatter.rich.nearby_chargers(data)


@vehicle_group.command("alerts")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def alerts_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show recent vehicle alerts."""
    run_async(_cmd_alerts(app_ctx, vin_positional))


async def _cmd_alerts(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        alerts = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.alerts",
            fetch=lambda: api.recent_alerts(vin),
            ttl=TTL_DEFAULT,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(alerts, command="vehicle.alerts")
    else:
        if alerts:
            for alert in alerts:
                name = alert.get("name", "Unknown")
                ts = alert.get("time", "")
                formatter.rich.info(f"  {name}  [dim]{ts}[/dim]")
        else:
            formatter.rich.info("[dim]No recent alerts.[/dim]")


@vehicle_group.command("release-notes")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def release_notes_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show firmware release notes."""
    run_async(_cmd_release_notes(app_ctx, vin_positional))


async def _cmd_release_notes(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.release-notes",
            fetch=lambda: api.release_notes(vin),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.release-notes")
    else:
        formatter.rich.vehicle_release_notes(data)


@vehicle_group.command("service")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def service_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show vehicle service data."""
    run_async(_cmd_service(app_ctx, vin_positional))


async def _cmd_service(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.service",
            fetch=lambda: api.service_data(vin),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.service")
    else:
        formatter.rich.vehicle_service(data)


@vehicle_group.command("drivers")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def drivers_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """List drivers associated with the vehicle."""
    run_async(_cmd_drivers(app_ctx, vin_positional))


async def _cmd_drivers(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        drivers = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.drivers",
            fetch=lambda: api.list_drivers(vin),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(drivers, command="vehicle.drivers")
    else:
        if drivers:
            for d in drivers:
                email = (d.get("email") if isinstance(d, dict) else d.email) or "unknown"
                status = (d.get("status") if isinstance(d, dict) else d.status) or ""
                formatter.rich.info(f"  {email}  [dim]{status}[/dim]")
        else:
            formatter.rich.info("[dim]No drivers found.[/dim]")


@vehicle_group.command("calendar")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("calendar_data")
@global_options
def calendar_cmd(app_ctx: AppContext, vin_positional: str | None, calendar_data: str) -> None:
    """Send calendar entries to the vehicle.

    CALENDAR_DATA should be a JSON string of calendar entries.
    """
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "upcoming_calendar_entries",
            "vehicle.calendar",
            body={"calendar_data": calendar_data},
        )
    )


# ---------------------------------------------------------------------------
# Power management commands
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Extended vehicle data endpoints
# ---------------------------------------------------------------------------


@vehicle_group.command("subscriptions")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def subscriptions_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Check subscription eligibility for the vehicle."""
    run_async(_cmd_subscriptions(app_ctx, vin_positional))


async def _cmd_subscriptions(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.subscriptions",
            fetch=lambda: api.eligible_subscriptions(vin),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.subscriptions")
    else:
        formatter.rich.vehicle_subscriptions(data)


@vehicle_group.command("upgrades")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def upgrades_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Check upgrade eligibility for the vehicle."""
    run_async(_cmd_upgrades(app_ctx, vin_positional))


async def _cmd_upgrades(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.upgrades",
            fetch=lambda: api.eligible_upgrades(vin),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.upgrades")
    else:
        formatter.rich.vehicle_upgrades(data)


@vehicle_group.command("options")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def options_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Fetch vehicle option codes."""
    run_async(_cmd_options(app_ctx, vin_positional))


async def _cmd_options(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.options",
            fetch=lambda: api.options(vin),
            ttl=TTL_STATIC,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.options")
    else:
        formatter.rich.vehicle_options(data)


@vehicle_group.command("specs")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def specs_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Fetch vehicle specifications (partner tokens, $0.10/call)."""
    run_async(_cmd_specs(app_ctx, vin_positional))


async def _cmd_specs(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.specs",
            fetch=lambda: api.specs(vin),
            ttl=TTL_STATIC,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.specs")
    else:
        formatter.rich.vehicle_specs(data)


@vehicle_group.command("warranty")
@global_options
def warranty_cmd(app_ctx: AppContext) -> None:
    """Fetch warranty details for the account."""
    run_async(_cmd_warranty(app_ctx))


async def _cmd_warranty(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="vehicle.warranty",
            fetch=lambda: api.warranty_details(),
            ttl=TTL_STATIC,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.warranty")
    else:
        formatter.rich.vehicle_warranty(data)


@vehicle_group.command("fleet-status")
@global_options
def fleet_status_cmd(app_ctx: AppContext) -> None:
    """Fetch fleet status for all vehicles."""
    run_async(_cmd_fleet_status(app_ctx))


async def _cmd_fleet_status(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="vehicle.fleet-status",
            fetch=lambda: api.fleet_status(),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.fleet-status")
    else:
        formatter.rich.fleet_status(data)


@telemetry_group.command("config")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def telemetry_config_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Fetch fleet telemetry configuration for a vehicle."""
    run_async(_cmd_telemetry_config(app_ctx, vin_positional))


async def _cmd_telemetry_config(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.telemetry.config",
            fetch=lambda: api.fleet_telemetry_config(vin),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.telemetry.config")
    else:
        formatter.rich.telemetry_config(data)


@telemetry_group.command("create")
@click.argument("config_json")
@global_options
def telemetry_config_create_cmd(app_ctx: AppContext, config_json: str) -> None:
    """Create or update fleet telemetry server configuration (CONFIG_JSON is a JSON string)."""
    import json

    from tescmd.api.errors import ConfigError

    try:
        config = json.loads(config_json)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in CONFIG_JSON: {e}") from e
    run_async(_cmd_telemetry_config_create(app_ctx, config))


async def _cmd_telemetry_config_create(app_ctx: AppContext, config: dict[str, object]) -> None:
    formatter = app_ctx.formatter
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await api.fleet_telemetry_config_create(config=config)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.telemetry.create")
    else:
        formatter.rich.info("Fleet telemetry config created/updated.")


@telemetry_group.command("delete")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--confirm",
    is_flag=True,
    required=True,
    help="Required flag to confirm config deletion",
)
@global_options
def telemetry_config_delete_cmd(
    app_ctx: AppContext, vin_positional: str | None, confirm: bool
) -> None:
    """Remove fleet telemetry configuration from a vehicle (DESTRUCTIVE).

    Requires --confirm flag.
    """
    run_async(_cmd_telemetry_config_delete(app_ctx, vin_positional))


async def _cmd_telemetry_config_delete(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await api.fleet_telemetry_config_delete(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.telemetry.delete")
    else:
        formatter.rich.info("Fleet telemetry config deleted.")


@telemetry_group.command("errors")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def telemetry_errors_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Fetch fleet telemetry errors for a vehicle."""
    run_async(_cmd_telemetry_errors(app_ctx, vin_positional))


async def _cmd_telemetry_errors(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="vin",
            identifier=vin,
            endpoint="vehicle.telemetry.errors",
            fetch=lambda: api.fleet_telemetry_errors(vin),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.telemetry.errors")
    else:
        formatter.rich.telemetry_errors(data)


@telemetry_group.command("stream")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--port", type=int, default=None, help="Local server port (random if omitted)")
@click.option("--fields", default="default", help="Field preset or comma-separated names")
@click.option("--interval", type=int, default=None, help="Override interval for all fields")
@global_options
def telemetry_stream_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    port: int | None,
    fields: str,
    interval: int | None,
) -> None:
    """Stream real-time telemetry via Tailscale Funnel.

    Starts a local WebSocket server, exposes it via Tailscale Funnel,
    configures the vehicle to push telemetry, and displays it in an
    interactive dashboard (TTY) or JSONL stream (piped).

    Requires: pip install tescmd[telemetry] and Tailscale (with Funnel enabled).
    """
    run_async(_cmd_telemetry_stream(app_ctx, vin_positional, port, fields, interval))


async def _noop_stop() -> None:
    """No-op tunnel cleanup (used when tunnel wasn't started yet)."""


async def _setup_tunnel(
    *,
    port: int,
    formatter: OutputFormatter,
) -> tuple[str, str, str, Callable[[], Awaitable[None]]]:
    """Start Tailscale Funnel and return ``(url, hostname, ca_pem, stop_fn)``."""
    from tescmd.telemetry.tailscale import TailscaleManager

    ts = TailscaleManager()
    await ts.check_available()
    await ts.check_running()

    url = await ts.start_funnel(port)
    if formatter.format != "json":
        formatter.rich.info(f"Tailscale Funnel active: {url}")

    hostname = await ts.get_hostname()
    ca_pem = await ts.get_cert_pem()
    return url, hostname, ca_pem, ts.stop_funnel


async def _cmd_telemetry_stream(
    app_ctx: AppContext,
    vin_positional: str | None,
    port: int | None,
    fields_spec: str,
    interval_override: int | None,
) -> None:
    from tescmd.telemetry.decoder import TelemetryDecoder
    from tescmd.telemetry.fields import resolve_fields
    from tescmd.telemetry.server import TelemetryServer

    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)

    # Pick a random high port if none specified
    if port is None:
        port = random.randint(49152, 65535)

    # Resolve fields
    field_config = resolve_fields(fields_spec, interval_override)

    # Build API client
    client, api = get_vehicle_api(app_ctx)
    decoder = TelemetryDecoder()

    # Output callback
    if formatter.format == "json":
        import json as json_mod

        async def on_frame(frame: TelemetryDecoder | object) -> None:
            from tescmd.telemetry.decoder import TelemetryFrame

            assert isinstance(frame, TelemetryFrame)
            line = json_mod.dumps(
                {
                    "vin": frame.vin,
                    "timestamp": frame.created_at.isoformat(),
                    "data": {d.field_name: d.value for d in frame.data},
                },
                default=str,
            )
            print(line, flush=True)

        dashboard = None
    else:
        from tescmd.telemetry.dashboard import TelemetryDashboard

        dashboard = TelemetryDashboard(formatter.console, formatter.rich._units)

        async def on_frame(frame: TelemetryDecoder | object) -> None:
            from tescmd.telemetry.decoder import TelemetryFrame

            assert isinstance(frame, TelemetryFrame)
            assert dashboard is not None
            dashboard.update(frame)

    # Load settings and public key before server creation — the key must be
    # served at /.well-known/ because Tesla fetches it during partner registration.
    from pathlib import Path

    from tescmd.crypto.keys import load_public_key_pem
    from tescmd.models.config import AppSettings

    _settings = AppSettings()
    key_dir = Path(_settings.config_dir).expanduser() / "keys"
    public_key_pem = load_public_key_pem(key_dir)

    # Server + Tunnel + Config with guaranteed cleanup
    server = TelemetryServer(
        port=port, decoder=decoder, on_frame=on_frame, public_key_pem=public_key_pem
    )
    tunnel_url: str | None = None
    config_created = False

    # Cleanup callbacks — set by tunnel provider
    stop_tunnel: Callable[[], Awaitable[None]] = _noop_stop
    original_partner_domain: str | None = None

    try:
        await server.start()

        if formatter.format != "json":
            formatter.rich.info(f"WebSocket server listening on port {port}")

        tunnel_url, hostname, ca_pem, stop_tunnel = await _setup_tunnel(
            port=port,
            formatter=formatter,
        )

        # --- Re-register partner domain if tunnel hostname differs ---
        registered_domain = (_settings.domain or "").lower().rstrip(".")
        tunnel_host = hostname.lower().rstrip(".")

        if tunnel_host != registered_domain:
            from tescmd.api.errors import AuthError
            from tescmd.auth.oauth import register_partner_account

            if not _settings.client_id or not _settings.client_secret:
                raise TunnelError(
                    "Client credentials required for partner domain "
                    "re-registration. Ensure TESLA_CLIENT_ID and "
                    "TESLA_CLIENT_SECRET are set."
                )

            reg_client_id = _settings.client_id
            reg_client_secret = _settings.client_secret
            region = app_ctx.region or _settings.region
            if formatter.format != "json":
                formatter.rich.info(f"Re-registering partner domain: {hostname}")

            async def _try_register() -> None:
                await register_partner_account(
                    client_id=reg_client_id,
                    client_secret=reg_client_secret,
                    domain=hostname,
                    region=region,
                )

            # Try registration with auto-retry for transient tunnel errors.
            # 412 = Allowed Origin URL missing in Developer Portal.
            # 424 = Tesla failed to reach the tunnel (key fetch failed) —
            #        typically a propagation delay after tunnel start.
            #        Tunnel propagation delays can cause transient failures,
            #        so we retry patiently (12 x 5s = 60s).
            max_retries = 12
            for attempt in range(max_retries):
                try:
                    await _try_register()
                    break
                except AuthError as exc:
                    status = getattr(exc, "status_code", None)

                    # 424 = key download failed — likely tunnel propagation delay
                    if status == 424 and attempt < max_retries - 1:
                        if formatter.format != "json":
                            formatter.rich.info(
                                f"[yellow]Waiting for tunnel to become reachable "
                                f"(HTTP 424)... "
                                f"({attempt + 1}/{max_retries})[/yellow]"
                            )
                        await asyncio.sleep(5)
                        continue

                    if status not in (412, 424):
                        raise TunnelError(
                            f"Partner re-registration failed for {hostname}: {exc}"
                        ) from exc

                    # 412 or exhausted 424 retries — need user intervention
                    if formatter.format == "json":
                        if status == 412:
                            raise TunnelError(
                                f"Add https://{hostname} as an Allowed Origin "
                                f"URL in your Tesla Developer Portal app, "
                                f"then try again."
                            ) from exc
                        raise TunnelError(
                            f"Tesla could not fetch the public key from "
                            f"https://{hostname}. Verify the tunnel is "
                            f"accessible and try again."
                        ) from exc

                    formatter.rich.info("")
                    if status == 412:
                        formatter.rich.info(
                            "[yellow]Tesla requires the tunnel domain as "
                            "an Allowed Origin URL.[/yellow]"
                        )
                    else:
                        formatter.rich.info(
                            "[yellow]Tesla could not reach the tunnel to "
                            "verify the public key (HTTP 424).[/yellow]"
                        )
                    formatter.rich.info("")
                    formatter.rich.info("  1. Open your Tesla Developer app:")
                    formatter.rich.info("     [cyan]https://developer.tesla.com[/cyan]")
                    formatter.rich.info("  2. Add this as an Allowed Origin URL:")
                    formatter.rich.info(f"     [cyan]https://{hostname}[/cyan]")
                    formatter.rich.info("  3. Save the changes")
                    formatter.rich.info("")

                    # Wait for user to fix, then retry
                    while True:
                        formatter.rich.info(
                            "Press [bold]Enter[/bold] when done (or Ctrl+C to cancel)..."
                        )
                        await asyncio.get_event_loop().run_in_executor(None, input)
                        try:
                            await _try_register()
                            break
                        except AuthError as retry_exc:
                            retry_status = getattr(retry_exc, "status_code", None)
                            if retry_status in (412, 424):
                                formatter.rich.info(
                                    f"[yellow]Tesla returned HTTP "
                                    f"{retry_status}. There is a propagation "
                                    f"delay on Tesla's end after adding an "
                                    f"Allowed Origin URL — this can take up "
                                    f"to 5 minutes.[/yellow]"
                                )
                                formatter.rich.info(
                                    "Press [bold]Enter[/bold] to retry, or "
                                    "wait and try again (Ctrl+C to cancel)..."
                                )
                                continue
                            raise TunnelError(
                                f"Partner re-registration failed: {retry_exc}"
                            ) from retry_exc
                    break  # registration succeeded in the inner loop

            original_partner_domain = _settings.domain

        # --- Common path: configure fleet telemetry ---
        inner_config: dict[str, object] = {
            "hostname": hostname,
            "port": 443,  # Tailscale Funnel terminates TLS on 443
            "ca": ca_pem,
            "fields": field_config,
            "alert_types": ["service"],
        }

        # Sign the config with the fleet key and use the JWS endpoint
        # (Tesla requires the Vehicle Command HTTP Proxy or JWS signing).
        from tescmd.api.errors import MissingScopesError
        from tescmd.crypto.keys import load_private_key
        from tescmd.crypto.schnorr import sign_fleet_telemetry_config

        private_key = load_private_key(key_dir)
        jws_token = sign_fleet_telemetry_config(private_key, inner_config)

        try:
            await api.fleet_telemetry_config_create_jws(vins=[vin], token=jws_token)
        except MissingScopesError:
            # Token lacks required scopes (e.g. vehicle_location was added
            # after the token was issued, or the partner domain changed).
            # A full re-login is needed — refresh alone doesn't update scopes.
            if formatter.format == "json":
                raise TunnelError(
                    "Your OAuth token is missing required scopes for "
                    "telemetry streaming. Run:\n"
                    "  1. tescmd auth register   (restore partner domain)\n"
                    "  2. tescmd auth login       (obtain token with updated scopes)\n"
                    "Then retry the stream command."
                ) from None

            from tescmd.auth.oauth import login_flow
            from tescmd.auth.token_store import TokenStore
            from tescmd.models.auth import DEFAULT_SCOPES

            formatter.rich.info("")
            formatter.rich.info(
                "[yellow]Token is missing required scopes — re-authenticating...[/yellow]"
            )
            formatter.rich.info("Opening your browser to sign in to Tesla...")
            formatter.rich.info(
                "When prompted, click [cyan]Select All[/cyan] and then"
                " [cyan]Allow[/cyan] to grant tescmd access."
            )

            login_port = 8085
            login_redirect = f"http://localhost:{login_port}/callback"
            login_store = TokenStore(
                profile=app_ctx.profile,
                token_file=_settings.token_file,
                config_dir=_settings.config_dir,
            )
            token_data = await login_flow(
                client_id=_settings.client_id or "",
                client_secret=_settings.client_secret,
                redirect_uri=login_redirect,
                scopes=DEFAULT_SCOPES,
                port=login_port,
                token_store=login_store,
                region=app_ctx.region or _settings.region,
            )
            client.update_token(token_data.access_token)
            formatter.rich.info("[green]Login successful — retrying config...[/green]")
            await api.fleet_telemetry_config_create_jws(vins=[vin], token=jws_token)

        config_created = True

        if formatter.format != "json":
            formatter.rich.info(f"Fleet telemetry configured for VIN {vin}")
            formatter.rich.info("")

        # Run dashboard or wait for interrupt
        if dashboard is not None:
            from rich.live import Live

            dashboard.set_tunnel_url(tunnel_url)
            with Live(
                dashboard,
                console=formatter.console,
                refresh_per_second=4,
            ) as live:
                dashboard.set_live(live)
                await _wait_for_interrupt()
        else:
            await _wait_for_interrupt()

    finally:
        # Cleanup in reverse order — each tolerates failure.
        # Show progress so the user knows what's happening on 'q'/Ctrl+C.
        is_rich = formatter.format != "json"

        if config_created:
            if is_rich:
                formatter.rich.info("[dim]Removing fleet telemetry config...[/dim]")
            try:
                await api.fleet_telemetry_config_delete(vin)
            except Exception:
                if is_rich:
                    formatter.rich.info(
                        "[yellow]Warning: failed to remove telemetry config."
                        " It may expire or can be removed manually.[/yellow]"
                    )

        if original_partner_domain is not None:
            if is_rich:
                formatter.rich.info(
                    f"[dim]Restoring partner domain to {original_partner_domain}...[/dim]"
                )
            try:
                from tescmd.auth.oauth import register_partner_account

                assert _settings.client_id is not None
                assert _settings.client_secret is not None
                await register_partner_account(
                    client_id=_settings.client_id,
                    client_secret=_settings.client_secret,
                    domain=original_partner_domain,
                    region=app_ctx.region or _settings.region,
                )
            except Exception:
                msg = (
                    f"Failed to restore partner domain to {original_partner_domain}. "
                    "Run 'tescmd auth register' to fix this manually."
                )
                logger.warning(msg)
                if is_rich:
                    formatter.rich.info(f"[yellow]Warning: {msg}[/yellow]")

        if is_rich:
            formatter.rich.info("[dim]Stopping tunnel...[/dim]")
        with contextlib.suppress(Exception):
            await stop_tunnel()

        if is_rich:
            formatter.rich.info("[dim]Stopping server...[/dim]")
        with contextlib.suppress(Exception):
            await server.stop()

        await client.close()
        if is_rich:
            formatter.rich.info("[green]Stream stopped.[/green]")


async def _wait_for_interrupt() -> None:
    """Block until Ctrl+C or 'q' is pressed."""
    import sys

    if not sys.stdin.isatty():
        # Non-TTY (piped / JSON mode): just wait for cancellation.
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        return

    try:
        import selectors
        import termios
        import tty
    except ImportError:
        # Non-Unix: fall back to Ctrl+C only.
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        return

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    sel = selectors.DefaultSelector()
    try:
        tty.setcbreak(fd)  # Chars available immediately; Ctrl+C still sends SIGINT
        sel.register(sys.stdin, selectors.EVENT_READ)
        while True:
            await asyncio.sleep(0.1)
            for _key, _ in sel.select(timeout=0):
                ch = sys.stdin.read(1)
                if ch in ("q", "Q"):
                    return
    except asyncio.CancelledError:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sel.close()


# ---------------------------------------------------------------------------
# Power management commands
# ---------------------------------------------------------------------------


@vehicle_group.command("low-power")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable low power mode")
@global_options
def low_power_cmd(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    """Enable or disable low power mode."""
    state = "enabled" if on else "disabled"
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "set_low_power_mode",
            "vehicle.low-power",
            body={"enable": on},
            success_message=f"Low power mode {state}.",
        )
    )


@vehicle_group.command("accessory-power")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Keep USB/outlets powered after exit")
@global_options
def accessory_power_cmd(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    """Keep accessory power (USB/outlets) active after exiting the vehicle."""
    state = "enabled" if on else "disabled"
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "keep_accessory_power_mode",
            "vehicle.accessory-power",
            body={"enable": on},
            success_message=f"Accessory power mode {state}.",
        )
    )
