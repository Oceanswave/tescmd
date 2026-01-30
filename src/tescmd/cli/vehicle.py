"""CLI commands for vehicle operations (list, info, data, location, wake)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import VehicleAsleepError
from tescmd.cli._client import (
    cached_vehicle_data,
    execute_command,
    get_vehicle_api,
    require_vin,
)
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext


# ---------------------------------------------------------------------------
# Command group
# ---------------------------------------------------------------------------

vehicle_group = click.Group("vehicle", help="Vehicle commands")


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
        vehicles = await api.list_vehicles()
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vehicles, command="vehicle.list")
    else:
        formatter.rich.vehicle_list(vehicles)


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
        enabled = await api.mobile_enabled(vin)
    finally:
        await client.close()

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
        data = await api.nearby_charging_sites(vin)
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
        alerts = await api.recent_alerts(vin)
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
        data = await api.release_notes(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.release-notes")
    else:
        if data:
            formatter.rich.info(str(data))
        else:
            formatter.rich.info("[dim]No release notes available.[/dim]")


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
        data = await api.service_data(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="vehicle.service")
    else:
        if data:
            formatter.rich.info(str(data))
        else:
            formatter.rich.info("[dim]No service data available.[/dim]")


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
        drivers = await api.list_drivers(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(drivers, command="vehicle.drivers")
    else:
        if drivers:
            for d in drivers:
                email = d.email or "unknown"
                status = d.status or ""
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
