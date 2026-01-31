"""CLI commands for software update management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import cached_vehicle_data, execute_command, get_vehicle_api, require_vin
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

software_group = click.Group("software", help="Software update commands")


@software_group.command("status")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def status_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show current software version and update status."""
    run_async(_cmd_status(app_ctx, vin_positional))


async def _cmd_status(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        vdata = await cached_vehicle_data(app_ctx, api, vin, endpoints=["vehicle_state"])
    finally:
        await client.close()

    if formatter.format == "json":
        vs = vdata.vehicle_state
        data: dict[str, Any] = {}
        if vs:
            data["car_version"] = vs.car_version
            data["software_update"] = vs.software_update
        formatter.output(data, command="software.status")
    else:
        if vdata.vehicle_state:
            formatter.rich.software_status(vdata.vehicle_state)
        else:
            formatter.rich.info("No vehicle state data available.")


@software_group.command("schedule")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("seconds", type=int)
@global_options
def schedule_cmd(app_ctx: AppContext, vin_positional: str | None, seconds: int) -> None:
    """Schedule a software update to install in SECONDS from now."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "schedule_software_update",
            "software.schedule",
            body={"offset_sec": seconds},
            success_message=f"Software update scheduled in {seconds}s.",
        )
    )


@software_group.command("cancel")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def cancel_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Cancel a pending software update."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "cancel_software_update",
            "software.cancel",
            success_message="Software update cancelled.",
        )
    )
