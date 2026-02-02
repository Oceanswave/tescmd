"""CLI commands for navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import (
    auto_wake,
    cached_vehicle_data,
    execute_command,
    get_command_api,
    get_vehicle_api,
    invalidate_cache_for_vin,
    require_vin,
)
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

nav_group = click.Group("nav", help="Navigation commands")


@nav_group.command("send")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("address", nargs=-1, required=True)
@global_options
def send_cmd(app_ctx: AppContext, vin_positional: str | None, address: tuple[str, ...]) -> None:
    """Send an address to the vehicle navigation.

    ADDRESS is the destination address (multiple words allowed).
    """
    full_address = " ".join(address)
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "share",
            "nav.send",
            body={"address": full_address},
            success_message="Destination sent to vehicle.",
        )
    )


@nav_group.command("gps")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("coords", nargs=-1, required=True)
@click.option("--order", type=int, default=None, help="Waypoint order (auto-increments for multi)")
@global_options
def gps_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    coords: tuple[str, ...],
    order: int | None,
) -> None:
    """Navigate to GPS coordinates.

    Accepts coordinates as LAT LON pairs or as comma-separated LAT,LON strings.

    Single point::

        tescmd nav gps 37.7749 122.4194
        tescmd nav gps 37.7749,122.4194
        tescmd nav gps 37.7749 122.4194 --order 1

    Multi-stop route (auto-ordered)::

        tescmd nav gps 37.7749,122.4194 37.3382,121.8863
    """
    run_async(_cmd_gps(app_ctx, vin_positional, coords, order))


def _parse_coords(coords: tuple[str, ...]) -> list[tuple[float, float]]:
    """Parse coordinate arguments into (lat, lon) pairs.

    Accepts either space-separated ``LAT LON`` pairs or comma-separated
    ``LAT,LON`` strings (or a mix).
    """
    points: list[tuple[float, float]] = []
    i = 0
    while i < len(coords):
        token = coords[i]
        if "," in token:
            parts = token.split(",", 1)
            points.append((float(parts[0]), float(parts[1])))
            i += 1
        elif i + 1 < len(coords) and "," not in coords[i + 1]:
            points.append((float(token), float(coords[i + 1])))
            i += 2
        else:
            raise click.UsageError(f"Invalid coordinate: {token!r}. Use 'LAT LON' or 'LAT,LON'.")
    return points


async def _cmd_gps(
    app_ctx: AppContext,
    vin_positional: str | None,
    coords: tuple[str, ...],
    order: int | None,
) -> None:
    points = _parse_coords(coords)

    if len(points) == 1:
        lat, lon = points[0]
        body: dict[str, object] = {"lat": lat, "lon": lon}
        if order is not None:
            body["order"] = order
        await execute_command(
            app_ctx,
            vin_positional,
            "navigation_gps_request",
            "nav.gps",
            body=body,
            success_message="GPS coordinates sent to vehicle.",
        )
    else:
        # Multi-point: send each with auto-incrementing order
        start_order = order if order is not None else 1
        for idx, (lat, lon) in enumerate(points):
            await execute_command(
                app_ctx,
                vin_positional,
                "navigation_gps_request",
                "nav.gps",
                body={"lat": lat, "lon": lon, "order": start_order + idx},
                success_message=f"GPS waypoint {start_order + idx} sent to vehicle.",
            )


@nav_group.command("supercharger")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def supercharger_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Navigate to the nearest Supercharger."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "navigation_sc_request",
            "nav.supercharger",
            success_message="Navigating to nearest Supercharger.",
        )
    )


@nav_group.command("homelink")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--lat", type=float, default=None, help="Latitude (auto-detected from vehicle if omitted)"
)
@click.option(
    "--lon", type=float, default=None, help="Longitude (auto-detected from vehicle if omitted)"
)
@global_options
def homelink_cmd(
    app_ctx: AppContext, vin_positional: str | None, lat: float | None, lon: float | None
) -> None:
    """Trigger HomeLink (garage door)."""
    run_async(_cmd_homelink(app_ctx, vin_positional, lat, lon))


async def _cmd_homelink(
    app_ctx: AppContext,
    vin_positional: str | None,
    lat: float | None,
    lon: float | None,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)

    # Auto-detect coordinates from vehicle drive_state if not provided
    if lat is None or lon is None:
        client, vehicle_api = get_vehicle_api(app_ctx)
        try:
            vdata = await cached_vehicle_data(
                app_ctx, vehicle_api, vin, endpoints=["drive_state", "location_data"]
            )
        finally:
            await client.close()

        ds = vdata.drive_state
        if ds and ds.latitude is not None and ds.longitude is not None:
            lat = ds.latitude
            lon = ds.longitude
        else:
            from tescmd.api.errors import ConfigError

            raise ConfigError(
                "Cannot detect vehicle location. Provide --lat and --lon explicitly."
            )

    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.trigger_homelink(vin, lat=lat, lon=lon),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="nav.homelink")
    else:
        msg = result.response.reason or "HomeLink triggered."
        formatter.rich.command_result(result.response.result, msg)


@nav_group.command("waypoints")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("place_ids", nargs=-1, required=True)
@global_options
def waypoints_cmd(
    app_ctx: AppContext, vin_positional: str | None, place_ids: tuple[str, ...]
) -> None:
    """Send multi-stop waypoints using Google Place IDs.

    PLACE_IDS are one or more Google Maps Place IDs.  Each ID is prefixed
    with ``refId:`` and joined into a comma-separated string before being
    sent to the vehicle.

    Example::

        tescmd nav waypoints ChIJIQBpAG2ahYAR_6128GcTUEo ChIJw____96GhYARCVVwg5cT7c0
    """
    waypoints_str = ",".join(f"refId:{pid}" for pid in place_ids)
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "navigation_waypoints_request",
            "nav.waypoints",
            body={"waypoints": waypoints_str},
            success_message="Waypoints sent to vehicle.",
        )
    )
