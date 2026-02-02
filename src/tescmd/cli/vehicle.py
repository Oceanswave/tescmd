"""CLI commands for vehicle operations (list, info, data, location, wake)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import VehicleAsleepError
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
from tescmd.models.sharing import ShareDriverInfo
from tescmd.models.vehicle import NearbyChargingSites, Vehicle

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext


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
            model_class=Vehicle,
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
            model_class=Vehicle,
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
        vdata = await cached_vehicle_data(
            app_ctx, api, vin, endpoints=["location_data"]
        )
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
            model_class=NearbyChargingSites,
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
                if isinstance(alert, dict):
                    name = alert.get("name", "Unknown")
                    ts = alert.get("time", "")
                    formatter.rich.info(f"  {name}  [dim]{ts}[/dim]")
                else:
                    formatter.rich.info(f"  {alert}")
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
            model_class=ShareDriverInfo,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(drivers, command="vehicle.drivers")
    else:
        if drivers:
            formatter.rich.info("[bold]Drivers[/bold]")
            for d in drivers:
                row = d if isinstance(d, dict) else d.model_dump(exclude_none=True)
                user_id = row.get("share_user_id", "")
                email = row.get("email") or "(no email)"
                status = row.get("status") or ""
                parts = [f"  {email}"]
                if status:
                    parts.append(f"[dim]{status}[/dim]")
                if user_id:
                    parts.append(f"[dim](id: {user_id})[/dim]")
                formatter.rich.info("  ".join(parts))
        else:
            formatter.rich.info("[dim]No drivers found.[/dim]")


@vehicle_group.command("calendar")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--file",
    "-f",
    "calendar_file",
    type=click.File("r"),
    default=None,
    help="Read calendar JSON from file (use '-' for stdin)",
)
@click.argument("calendar_data", required=False, default=None)
@global_options
def calendar_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    calendar_file: click.utils.LazyFile | None,
    calendar_data: str | None,
) -> None:
    """Send calendar entries to the vehicle.

    Pass calendar JSON as an argument, via --file, or piped through stdin.

    \b
    Example JSON:
      {
        "calendars": [{
          "name": "Work",
          "color": "#4285F4",
          "events": [{
            "name": "Team Standup",
            "location": "1 Market St, San Francisco, CA",
            "start": 1738573200000,
            "end": 1738576800000,
            "all_day": false,
            "organizer": "alice@example.com"
          }]
        }],
        "phone_name": "My Phone",
        "uuid": "abc-123"
      }

    \b
    Usage:
      tescmd vehicle calendar --file cal.json
      tescmd vehicle calendar '{"calendars": [...]}'
      cat cal.json | tescmd vehicle calendar --file -
    """
    import sys

    if calendar_file is not None:
        data = calendar_file.read()  # type: ignore[union-attr]
    elif calendar_data is not None:
        data = calendar_data
    elif not sys.stdin.isatty():
        data = sys.stdin.read()
    else:
        raise click.UsageError(
            "No calendar data provided.\n\n"
            "Usage:\n"
            "  tescmd vehicle calendar --file cal.json\n"
            "  tescmd vehicle calendar '{\"calendars\": [...]}'\n"
            "  cat cal.json | tescmd vehicle calendar --file -\n\n"
            "Run --help for a full JSON example."
        )

    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "upcoming_calendar_entries",
            "vehicle.calendar",
            body={"calendar_data": data.strip()},
        )
    )


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
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def warranty_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Fetch warranty details for the vehicle."""
    run_async(_cmd_warranty(app_ctx, vin_positional))


async def _cmd_warranty(app_ctx: AppContext, vin_positional: str | None) -> None:
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
@click.option(
    "--port",
    "telemetry_port",
    type=int,
    default=None,
    help="Local server port (random if omitted)",
)
@click.option("--fields", default="default", help="Field preset or comma-separated names")
@click.option("--interval", type=int, default=None, help="Override interval for all fields")
@click.option("--no-log", is_flag=True, default=False, help="Disable CSV telemetry log")
@click.option(
    "--legacy-dashboard",
    is_flag=True,
    default=False,
    help="Use legacy Rich Live dashboard",
)
@global_options
def telemetry_stream_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    telemetry_port: int | None,
    fields: str,
    interval: int | None,
    no_log: bool,
    legacy_dashboard: bool,
) -> None:
    """Stream real-time telemetry via Tailscale Funnel.

    Alias for ``tescmd serve --no-mcp``.  Starts a local WebSocket server,
    exposes it via Tailscale Funnel, configures the vehicle to push
    telemetry, and displays a full-screen TUI dashboard (TTY) or JSONL
    stream (piped).  A CSV log is written by default.

    Requires Tailscale with Funnel enabled.
    """
    from tescmd.cli.serve import _cmd_serve

    run_async(
        _cmd_serve(
            app_ctx,
            vin_positional=vin_positional,
            transport="streamable-http",
            mcp_port=int(os.environ.get("TESCMD_MCP_PORT", "8080")),
            telemetry_port=telemetry_port,
            fields_spec=fields,
            interval_override=interval,
            no_telemetry=False,
            no_mcp=True,
            no_log=no_log,
            legacy_dashboard=legacy_dashboard,
            openclaw_url=None,
            openclaw_token=None,
            openclaw_config_path=None,
            dry_run=False,
            tailscale=False,
            client_id="",
            client_secret="",
        )
    )


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
