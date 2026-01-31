"""CLI commands for charging operations."""

from __future__ import annotations

import json
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

charge_group = click.Group("charge", help="Charging commands")


# ---------------------------------------------------------------------------
# Status (read via VehicleAPI)
# ---------------------------------------------------------------------------


@charge_group.command("status")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def status_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show current charging status."""
    run_async(_cmd_status(app_ctx, vin_positional))


async def _cmd_status(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        vdata = await cached_vehicle_data(app_ctx, api, vin, endpoints=["charge_state"])
    finally:
        await client.close()

    if formatter.format == "json":
        cs = vdata.charge_state
        formatter.output(
            cs.model_dump(exclude_none=True) if cs else {},
            command="charge.status",
        )
    else:
        if vdata.charge_state:
            formatter.rich.charge_status(vdata.charge_state)
        else:
            formatter.rich.info("No charge state data available.")


# ---------------------------------------------------------------------------
# Simple commands (write via CommandAPI)
# ---------------------------------------------------------------------------


@charge_group.command("start")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def start_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Start charging."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "charge_start",
            "charge.start",
            success_message="Charging started.",
        )
    )


@charge_group.command("stop")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def stop_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Stop charging."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "charge_stop",
            "charge.stop",
            success_message="Charging stopped.",
        )
    )


@charge_group.command("limit-max")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def limit_max_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Set charge limit to maximum range."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "charge_max_range",
            "charge.limit-max",
            success_message="Charge limit set to maximum range.",
        )
    )


@charge_group.command("limit-std")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def limit_std_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Set charge limit to standard range."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "charge_standard",
            "charge.limit-std",
            success_message="Charge limit set to standard range.",
        )
    )


@charge_group.command("port-open")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def port_open_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Open the charge port door."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "charge_port_door_open",
            "charge.port-open",
            success_message="Charge port opened.",
        )
    )


@charge_group.command("port-close")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def port_close_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Close the charge port door."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "charge_port_door_close",
            "charge.port-close",
            success_message="Charge port closed.",
        )
    )


# ---------------------------------------------------------------------------
# Parameterised commands
# ---------------------------------------------------------------------------


@charge_group.command("limit")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("percent", type=click.IntRange(50, 100))
@global_options
def limit_cmd(app_ctx: AppContext, vin_positional: str | None, percent: int) -> None:
    """Set charge limit to PERCENT (50-100)."""
    run_async(_cmd_limit(app_ctx, vin_positional, percent))


async def _cmd_limit(app_ctx: AppContext, vin_positional: str | None, percent: int) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_charge_limit(vin, percent=percent),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="charge.limit")
    else:
        msg = result.response.reason or f"Charge limit set to {percent}%."
        formatter.rich.command_result(result.response.result, msg)


@charge_group.command("amps")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("amps", type=click.IntRange(0, 48))
@global_options
def amps_cmd(app_ctx: AppContext, vin_positional: str | None, amps: int) -> None:
    """Set charging current to AMPS (0-48)."""
    run_async(_cmd_amps(app_ctx, vin_positional, amps))


async def _cmd_amps(app_ctx: AppContext, vin_positional: str | None, amps: int) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_charging_amps(vin, charging_amps=amps),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="charge.amps")
    else:
        msg = result.response.reason or f"Charging current set to {amps}A."
        formatter.rich.command_result(result.response.result, msg)


@charge_group.command("schedule")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--enable/--disable", default=True, help="Enable or disable scheduled charging")
@click.option(
    "--time",
    "time_minutes",
    type=int,
    default=0,
    help="Scheduled start time in minutes past midnight",
)
@global_options
def schedule_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    enable: bool,
    time_minutes: int,
) -> None:
    """Configure scheduled charging."""
    run_async(_cmd_schedule(app_ctx, vin_positional, enable, time_minutes))


async def _cmd_schedule(
    app_ctx: AppContext,
    vin_positional: str | None,
    enable: bool,
    time_minutes: int,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_scheduled_charging(vin, enable=enable, time=time_minutes),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="charge.schedule")
    else:
        state = "enabled" if enable else "disabled"
        msg = result.response.reason or f"Scheduled charging {state}."
        formatter.rich.command_result(result.response.result, msg)


# ---------------------------------------------------------------------------
# Scheduled departure / precondition schedules
# ---------------------------------------------------------------------------


@charge_group.command("departure")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--time", "departure_time", type=int, required=True, help="Departure time (mins past midnight)"
)
@click.option("--on/--off", "enable", default=True, help="Enable or disable scheduled departure")
@click.option("--precondition", is_flag=True, default=False, help="Enable preconditioning")
@click.option(
    "--precondition-weekdays", is_flag=True, default=False, help="Preconditioning weekdays only"
)
@click.option("--off-peak", is_flag=True, default=False, help="Enable off-peak charging")
@click.option("--off-peak-weekdays", is_flag=True, default=False, help="Off-peak weekdays only")
@click.option("--off-peak-end", type=int, default=0, help="End off-peak time (mins past midnight)")
@global_options
def departure_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    departure_time: int,
    enable: bool,
    precondition: bool,
    precondition_weekdays: bool,
    off_peak: bool,
    off_peak_weekdays: bool,
    off_peak_end: int,
) -> None:
    """Configure scheduled departure."""
    run_async(
        _cmd_departure(
            app_ctx,
            vin_positional,
            enable,
            departure_time,
            precondition,
            precondition_weekdays,
            off_peak,
            off_peak_weekdays,
            off_peak_end,
        )
    )


async def _cmd_departure(
    app_ctx: AppContext,
    vin_positional: str | None,
    enable: bool,
    departure_time: int,
    precondition: bool,
    precondition_weekdays: bool,
    off_peak: bool,
    off_peak_weekdays: bool,
    off_peak_end: int,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_scheduled_departure(
                vin,
                enable=enable,
                departure_time=departure_time,
                preconditioning_enabled=precondition,
                preconditioning_weekdays_only=precondition_weekdays,
                off_peak_charging_enabled=off_peak,
                off_peak_charging_weekdays_only=off_peak_weekdays,
                end_off_peak_time=off_peak_end,
            ),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="charge.departure")
    else:
        state = "enabled" if enable else "disabled"
        msg = result.response.reason or f"Scheduled departure {state}."
        formatter.rich.command_result(result.response.result, msg)


@charge_group.command("precondition-add")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("schedule_json")
@global_options
def precondition_add_cmd(
    app_ctx: AppContext, vin_positional: str | None, schedule_json: str
) -> None:
    """Add a precondition schedule (SCHEDULE_JSON is a JSON string)."""
    schedule = json.loads(schedule_json)
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "add_precondition_schedule",
            "charge.precondition-add",
            body=schedule,
            success_message="Precondition schedule added.",
        )
    )


@charge_group.command("precondition-remove")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("schedule_id", type=int)
@global_options
def precondition_remove_cmd(
    app_ctx: AppContext, vin_positional: str | None, schedule_id: int
) -> None:
    """Remove a precondition schedule by ID."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "remove_precondition_schedule",
            "charge.precondition-remove",
            body={"id": schedule_id},
            success_message="Precondition schedule removed.",
        )
    )


# ---------------------------------------------------------------------------
# Charge schedule management (firmware 2024.26+)
# ---------------------------------------------------------------------------


@charge_group.command("add-schedule")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--id", "schedule_id", type=int, required=True, help="Schedule ID")
@click.option("--name", default=None, help="Schedule name")
@click.option(
    "--days-of-week",
    default=None,
    help="Days of week bitmask (e.g. 127 for all days)",
)
@click.option("--start-time", type=int, default=None, help="Start time (minutes past midnight)")
@click.option("--end-time", type=int, default=None, help="End time (minutes past midnight)")
@click.option("--enabled/--disabled", default=True, help="Enable or disable the schedule")
@click.option("--one-time", is_flag=True, default=False, help="One-time schedule")
@global_options
def add_schedule_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    schedule_id: int,
    name: str | None,
    days_of_week: str | None,
    start_time: int | None,
    end_time: int | None,
    enabled: bool,
    one_time: bool,
) -> None:
    """Add or update a charge schedule (firmware 2024.26+)."""
    schedule: dict[str, object] = {"id": schedule_id, "enabled": enabled}
    if name is not None:
        schedule["name"] = name
    if days_of_week is not None:
        schedule["days_of_week"] = int(days_of_week)
    if start_time is not None:
        schedule["start_time"] = start_time
    if end_time is not None:
        schedule["end_time"] = end_time
    if one_time:
        schedule["one_time"] = True
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "add_charge_schedule",
            "charge.add-schedule",
            body={"schedule": json.dumps(schedule)},
            success_message="Charge schedule updated.",
        )
    )


@charge_group.command("remove-schedule")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--id", "schedule_id", type=int, required=True, help="Schedule ID to remove")
@global_options
def remove_schedule_cmd(app_ctx: AppContext, vin_positional: str | None, schedule_id: int) -> None:
    """Remove a charge schedule (firmware 2024.26+)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "remove_charge_schedule",
            "charge.remove-schedule",
            body={"id": schedule_id},
            success_message="Charge schedule removed.",
        )
    )


# ---------------------------------------------------------------------------
# Managed charging (fleet)
# ---------------------------------------------------------------------------


@charge_group.command("managed-amps")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("amps", type=int)
@global_options
def managed_amps_cmd(app_ctx: AppContext, vin_positional: str | None, amps: int) -> None:
    """Set managed charging current in amps (fleet management)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "set_managed_charge_current_request",
            "charge.managed-amps",
            body={"charging_amps": amps},
            success_message=f"Managed charging current set to {amps}A.",
        )
    )
