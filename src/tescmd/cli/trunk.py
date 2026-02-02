"""CLI commands for trunk and window operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import (
    auto_wake,
    execute_command,
    get_command_api,
    invalidate_cache_for_vin,
    require_vin,
)
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext
    from tescmd.models.command import CommandResponse

trunk_group = click.Group("trunk", help="Trunk and window commands")


# ---------------------------------------------------------------------------
# Trunk commands
# ---------------------------------------------------------------------------


@trunk_group.command("open")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def open_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Open (toggle) the rear trunk."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "actuate_trunk",
            "trunk.open",
            body={"which_trunk": "rear"},
            success_message="Rear trunk opened.",
        )
    )


@trunk_group.command("close")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def close_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Close (toggle) the rear trunk.

    Note: actuate_trunk is a toggle — open and close both call the same endpoint.
    """
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "actuate_trunk",
            "trunk.close",
            body={"which_trunk": "rear"},
            success_message="Rear trunk closed.",
        )
    )


@trunk_group.command("frunk")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def frunk_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Open the front trunk (frunk)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "actuate_trunk",
            "trunk.frunk",
            body={"which_trunk": "front"},
            success_message="Frunk opened.",
        )
    )


# ---------------------------------------------------------------------------
# Sunroof command
# ---------------------------------------------------------------------------


@trunk_group.command("sunroof")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--state",
    type=click.Choice(["vent", "close", "stop"]),
    required=True,
    help="Sunroof action: vent, close, or stop",
)
@global_options
def sunroof_cmd(app_ctx: AppContext, vin_positional: str | None, state: str) -> None:
    """Control the panoramic sunroof (vent, close, or stop)."""
    messages = {"vent": "Sunroof vented.", "close": "Sunroof closed.", "stop": "Sunroof stopped."}
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "sun_roof_control",
            "trunk.sunroof",
            body={"state": state},
            success_message=messages[state],
        )
    )


# ---------------------------------------------------------------------------
# Tonneau cover commands (Cybertruck)
# ---------------------------------------------------------------------------


@trunk_group.command("tonneau-open")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def tonneau_open_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Open the Cybertruck tonneau cover."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "open_tonneau",
            "trunk.tonneau-open",
            success_message="Tonneau cover opening.",
        )
    )


@trunk_group.command("tonneau-close")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def tonneau_close_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Close the Cybertruck tonneau cover."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "close_tonneau",
            "trunk.tonneau-close",
            success_message="Tonneau cover closing.",
        )
    )


@trunk_group.command("tonneau-stop")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def tonneau_stop_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Stop the Cybertruck tonneau cover movement."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "stop_tonneau",
            "trunk.tonneau-stop",
            success_message="Tonneau cover stopped.",
        )
    )


# ---------------------------------------------------------------------------
# Window command
# ---------------------------------------------------------------------------


@trunk_group.command("window")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--vent/--close", "vent", default=True, help="Vent or close windows")
@click.option("--lat", type=float, default=None, help="Vehicle latitude (for close)")
@click.option("--lon", type=float, default=None, help="Vehicle longitude (for close)")
@global_options
def window_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    vent: bool,
    lat: float | None,
    lon: float | None,
) -> None:
    """Vent or close all windows.

    Closing windows requires vehicle coordinates. If --lat/--lon are not
    provided, the vehicle's current location will be fetched automatically.
    """
    run_async(_cmd_window(app_ctx, vin_positional, vent, lat, lon))


async def _cmd_window(
    app_ctx: AppContext,
    vin_positional: str | None,
    vent: bool,
    lat: float | None,
    lon: float | None,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:

        async def _execute_window() -> CommandResponse:
            if vent:
                cmd_str = "vent"
                use_lat = lat if lat is not None else 0.0
                use_lon = lon if lon is not None else 0.0
            else:
                cmd_str = "close"
                if lat is not None and lon is not None:
                    use_lat, use_lon = lat, lon
                else:
                    vdata = await vehicle_api.get_vehicle_data(
                        vin, endpoints=["drive_state", "location_data"]
                    )
                    ds = vdata.drive_state
                    if ds and ds.latitude is not None and ds.longitude is not None:
                        use_lat, use_lon = ds.latitude, ds.longitude
                    else:
                        use_lat, use_lon = 0.0, 0.0
            return await cmd_api.window_control(vin, command=cmd_str, lat=use_lat, lon=use_lon)

        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            _execute_window,
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="trunk.window")
    else:
        action = "vented" if vent else "closed"
        msg = result.response.reason or f"Windows {action}."
        formatter.rich.command_result(result.response.result, msg)
