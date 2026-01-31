"""CLI commands for climate operations."""

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

climate_group = click.Group("climate", help="Climate and comfort commands")

# Tesla's internal seat position indices
SEAT_MAP: dict[str, int] = {
    "driver": 0,
    "passenger": 1,
    "rear-left": 2,
    "rear-center": 4,
    "rear-right": 5,
}

# Climate keeper mode string → integer
KEEPER_MODE_MAP: dict[str, int] = {
    "off": 0,
    "on": 1,
    "dog": 2,
    "camp": 3,
}


def _f_to_c(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (fahrenheit - 32.0) * 5.0 / 9.0


# ---------------------------------------------------------------------------
# Status (read via VehicleAPI)
# ---------------------------------------------------------------------------


@climate_group.command("status")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def status_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show current climate status."""
    run_async(_cmd_status(app_ctx, vin_positional))


async def _cmd_status(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_vehicle_api(app_ctx)
    try:
        vdata = await cached_vehicle_data(app_ctx, api, vin, endpoints=["climate_state"])
    finally:
        await client.close()

    if formatter.format == "json":
        cs = vdata.climate_state
        formatter.output(
            cs.model_dump(exclude_none=True) if cs else {},
            command="climate.status",
        )
    else:
        if vdata.climate_state:
            formatter.rich.climate_status(vdata.climate_state)
        else:
            formatter.rich.info("No climate state data available.")


# ---------------------------------------------------------------------------
# Simple on/off commands
# ---------------------------------------------------------------------------


@climate_group.command("on")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def on_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Turn on climate control (auto conditioning)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "auto_conditioning_start",
            "climate.on",
            success_message="Climate control turned on.",
        )
    )


@climate_group.command("off")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def off_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Turn off climate control (auto conditioning)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "auto_conditioning_stop",
            "climate.off",
            success_message="Climate control turned off.",
        )
    )


# ---------------------------------------------------------------------------
# Parameterised commands
# ---------------------------------------------------------------------------


@climate_group.command("set")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("temp", type=float)
@click.option("--passenger", type=float, default=None, help="Separate passenger temperature")
@click.option("--celsius", is_flag=True, default=False, help="Input temperature is in Celsius")
@global_options
def set_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    temp: float,
    passenger: float | None,
    celsius: bool,
) -> None:
    """Set cabin temperature to TEMP (default: Fahrenheit)."""
    run_async(_cmd_set(app_ctx, vin_positional, temp, passenger, celsius))


async def _cmd_set(
    app_ctx: AppContext,
    vin_positional: str | None,
    temp: float,
    passenger: float | None,
    celsius: bool,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)

    driver_c = temp if celsius else _f_to_c(temp)
    passenger_c = driver_c
    if passenger is not None:
        passenger_c = passenger if celsius else _f_to_c(passenger)

    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_temps(vin, driver_temp=driver_c, passenger_temp=passenger_c),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="climate.set")
    else:
        msg = result.response.reason or "Temperature set."
        formatter.rich.command_result(result.response.result, msg)


@climate_group.command("precondition")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable max preconditioning")
@global_options
def precondition_cmd(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    """Enable or disable max preconditioning."""
    run_async(_cmd_precondition(app_ctx, vin_positional, on))


async def _cmd_precondition(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_preconditioning_max(vin, on=on),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="climate.precondition")
    else:
        state = "enabled" if on else "disabled"
        msg = result.response.reason or f"Max preconditioning {state}."
        formatter.rich.command_result(result.response.result, msg)


@climate_group.command("seat")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("seat", type=click.Choice(list(SEAT_MAP)))
@click.argument("level", type=click.IntRange(0, 3))
@global_options
def seat_cmd(app_ctx: AppContext, vin_positional: str | None, seat: str, level: int) -> None:
    """Set seat heater for SEAT to LEVEL (0-3)."""
    run_async(_cmd_seat(app_ctx, vin_positional, seat, level))


async def _cmd_seat(
    app_ctx: AppContext,
    vin_positional: str | None,
    seat: str,
    level: int,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.remote_seat_heater_request(vin, heater=SEAT_MAP[seat], level=level),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="climate.seat")
    else:
        msg = result.response.reason or f"Seat heater set for {seat} (level {level})."
        formatter.rich.command_result(result.response.result, msg)


@climate_group.command("seat-cool")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("seat", type=click.Choice(list(SEAT_MAP)))
@click.argument("level", type=click.IntRange(0, 3))
@global_options
def seat_cool_cmd(app_ctx: AppContext, vin_positional: str | None, seat: str, level: int) -> None:
    """Set seat cooler for SEAT to LEVEL (0-3)."""
    run_async(_cmd_seat_cool(app_ctx, vin_positional, seat, level))


async def _cmd_seat_cool(
    app_ctx: AppContext,
    vin_positional: str | None,
    seat: str,
    level: int,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.remote_seat_cooler_request(
                vin, seat_position=SEAT_MAP[seat], seat_cooler_level=level
            ),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="climate.seat-cool")
    else:
        msg = result.response.reason or f"Seat cooler set for {seat} (level {level})."
        formatter.rich.command_result(result.response.result, msg)


@climate_group.command("wheel-heater")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable steering wheel heater")
@global_options
def wheel_heater_cmd(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    """Enable or disable steering wheel heater."""
    run_async(_cmd_wheel_heater(app_ctx, vin_positional, on))


async def _cmd_wheel_heater(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.remote_steering_wheel_heater_request(vin, on=on),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="climate.wheel-heater")
    else:
        state = "enabled" if on else "disabled"
        msg = result.response.reason or f"Steering wheel heater {state}."
        formatter.rich.command_result(result.response.result, msg)


@climate_group.command("overheat")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable cabin overheat protection")
@click.option("--fan-only", is_flag=True, default=False, help="Use fan only (no AC)")
@global_options
def overheat_cmd(
    app_ctx: AppContext, vin_positional: str | None, on: bool, fan_only: bool
) -> None:
    """Configure cabin overheat protection."""
    run_async(_cmd_overheat(app_ctx, vin_positional, on, fan_only))


async def _cmd_overheat(
    app_ctx: AppContext,
    vin_positional: str | None,
    on: bool,
    fan_only: bool,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_cabin_overheat_protection(vin, on=on, fan_only=fan_only),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="climate.overheat")
    else:
        state = "enabled" if on else "disabled"
        msg = result.response.reason or f"Cabin overheat protection {state}."
        formatter.rich.command_result(result.response.result, msg)


@climate_group.command("bioweapon")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable bioweapon defense mode")
@click.option("--manual-override", is_flag=True, default=False, help="Force manual override")
@global_options
def bioweapon_cmd(
    app_ctx: AppContext, vin_positional: str | None, on: bool, manual_override: bool
) -> None:
    """Enable or disable bioweapon defense mode."""
    state = "enabled" if on else "disabled"
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "set_bioweapon_mode",
            "climate.bioweapon",
            body={"on": on, "manual_override": manual_override},
            success_message=f"Bioweapon defense mode {state}.",
        )
    )


@climate_group.command("cop-temp")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("level", type=click.IntRange(0, 2))
@global_options
def cop_temp_cmd(app_ctx: AppContext, vin_positional: str | None, level: int) -> None:
    """Set cabin overheat protection temperature (0=low, 1=medium, 2=high)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "set_cop_temp",
            "climate.cop-temp",
            body={"cop_temp": level},
            success_message="Overheat protection temperature set.",
        )
    )


@climate_group.command("auto-seat")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("seat", type=click.Choice(list(SEAT_MAP)))
@click.option("--on/--off", default=True, help="Enable or disable auto seat climate")
@global_options
def auto_seat_cmd(app_ctx: AppContext, vin_positional: str | None, seat: str, on: bool) -> None:
    """Enable or disable auto seat climate for SEAT."""
    state = "enabled" if on else "disabled"
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "remote_auto_seat_climate_request",
            "climate.auto-seat",
            body={"auto_seat_position": SEAT_MAP[seat], "on": on},
            success_message=f"Auto seat climate {state} for {seat}.",
        )
    )


@climate_group.command("auto-wheel")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable auto steering wheel heat")
@global_options
def auto_wheel_cmd(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    """Enable or disable auto steering wheel heat."""
    state = "enabled" if on else "disabled"
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "remote_auto_steering_wheel_heat_climate_request",
            "climate.auto-wheel",
            body={"on": on},
            success_message=f"Auto steering wheel heat {state}.",
        )
    )


@climate_group.command("wheel-level")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("level", type=click.IntRange(0, 3))
@global_options
def wheel_level_cmd(app_ctx: AppContext, vin_positional: str | None, level: int) -> None:
    """Set steering wheel heat level (0=off, 1=low, 2=med, 3=high)."""
    level_names = {0: "off", 1: "low", 2: "medium", 3: "high"}
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "remote_steering_wheel_heat_level_request",
            "climate.wheel-level",
            body={"level": level},
            success_message=f"Steering wheel heat set to {level_names.get(level, level)}.",
        )
    )


@climate_group.command("keeper")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("mode", type=click.Choice(list(KEEPER_MODE_MAP)))
@global_options
def keeper_cmd(app_ctx: AppContext, vin_positional: str | None, mode: str) -> None:
    """Set climate keeper mode (off/on/dog/camp)."""
    run_async(_cmd_keeper(app_ctx, vin_positional, mode))


async def _cmd_keeper(app_ctx: AppContext, vin_positional: str | None, mode: str) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_climate_keeper_mode(
                vin, climate_keeper_mode=KEEPER_MODE_MAP[mode]
            ),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="climate.keeper")
    else:
        msg = result.response.reason or f"Climate keeper mode set to {mode}."
        formatter.rich.command_result(result.response.result, msg)
