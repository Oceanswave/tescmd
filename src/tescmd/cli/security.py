"""CLI commands for security operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.api.errors import ConfigError
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

security_group = click.Group("security", help="Security and access commands")


# ---------------------------------------------------------------------------
# Status (read via VehicleAPI)
# ---------------------------------------------------------------------------


@security_group.command("status")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def status_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Show current security status (locks, sentry, etc.)."""
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
        formatter.output(
            vs.model_dump(exclude_none=True) if vs else {},
            command="security.status",
        )
    else:
        if vdata.vehicle_state:
            formatter.rich.vehicle_status(vdata.vehicle_state)
        else:
            formatter.rich.info("No vehicle state data available.")


# ---------------------------------------------------------------------------
# Simple commands
# ---------------------------------------------------------------------------


@security_group.command("lock")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def lock_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Lock all doors."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "door_lock",
            "security.lock",
            success_message="Doors locked.",
        )
    )


@security_group.command("unlock")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def unlock_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Unlock all doors."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "door_unlock",
            "security.unlock",
            success_message="Doors unlocked.",
        )
    )


@security_group.command("valet-reset")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def valet_reset_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Reset valet PIN."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "reset_valet_pin",
            "security.valet-reset",
            success_message="Valet PIN reset.",
        )
    )


@security_group.command("remote-start")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def remote_start_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Enable remote start."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "remote_start_drive",
            "security.remote-start",
            success_message="Remote start enabled.",
        )
    )


@security_group.command("flash")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def flash_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Flash the vehicle lights."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "flash_lights",
            "security.flash",
            success_message="Lights flashed.",
        )
    )


@security_group.command("honk")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def honk_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Honk the horn."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "honk_horn",
            "security.honk",
            success_message="Horn honked.",
        )
    )


# ---------------------------------------------------------------------------
# Parameterised commands
# ---------------------------------------------------------------------------


@security_group.command("sentry")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable sentry mode")
@global_options
def sentry_cmd(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    """Enable or disable sentry mode."""
    run_async(_cmd_sentry(app_ctx, vin_positional, on))


async def _cmd_sentry(app_ctx: AppContext, vin_positional: str | None, on: bool) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_sentry_mode(vin, on=on),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="security.sentry")
    else:
        state = "enabled" if on else "disabled"
        msg = result.response.reason or f"Sentry mode {state}."
        formatter.rich.command_result(result.response.result, msg)


@security_group.command("valet")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable valet mode")
@click.option("--password", default=None, help="Valet PIN")
@global_options
def valet_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    on: bool,
    password: str | None,
) -> None:
    """Enable or disable valet mode."""
    run_async(_cmd_valet(app_ctx, vin_positional, on, password))


async def _cmd_valet(
    app_ctx: AppContext,
    vin_positional: str | None,
    on: bool,
    password: str | None,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: cmd_api.set_valet_mode(vin, on=on, password=password),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command="security.valet")
    else:
        state = "enabled" if on else "disabled"
        msg = result.response.reason or f"Valet mode {state}."
        formatter.rich.command_result(result.response.result, msg)


@security_group.command("pin-to-drive")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", default=True, help="Enable or disable PIN to Drive")
@click.option("--password", default=None, help="PIN code")
@global_options
def pin_to_drive_cmd(
    app_ctx: AppContext, vin_positional: str | None, on: bool, password: str | None
) -> None:
    """Enable or disable PIN to Drive."""
    body: dict[str, object] = {"on": on}
    if password is not None:
        body["password"] = password
    state = "enabled" if on else "disabled"
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "set_pin_to_drive",
            "security.pin-to-drive",
            body=body,
            success_message=f"PIN to Drive {state}.",
        )
    )


@security_group.command("guest-mode")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--on/--off", "enable", default=True, help="Enable or disable guest mode")
@global_options
def guest_mode_cmd(app_ctx: AppContext, vin_positional: str | None, enable: bool) -> None:
    """Enable or disable guest mode."""
    state = "enabled" if enable else "disabled"
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "guest_mode",
            "security.guest-mode",
            body={"enable": enable},
            success_message=f"Guest mode {state}.",
        )
    )


@security_group.command("erase-data")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--confirm",
    is_flag=True,
    required=True,
    help="Required flag to confirm data erasure (DESTRUCTIVE)",
)
@global_options
def erase_data_cmd(app_ctx: AppContext, vin_positional: str | None, confirm: bool) -> None:
    """Erase all user data from the vehicle (DESTRUCTIVE).

    Requires --confirm flag.
    """
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "erase_user_data",
            "security.erase-data",
            success_message="User data erased.",
        )
    )


@security_group.command("boombox")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option(
    "--sound",
    type=click.Choice(["locate", "fart"]),
    default="locate",
    help="Sound to play (locate=ping, fart=random fart)",
)
@global_options
def boombox_cmd(app_ctx: AppContext, vin_positional: str | None, sound: str) -> None:
    """Activate the boombox (external speaker)."""
    sound_id = 0 if sound == "fart" else 2000
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "remote_boombox",
            "security.boombox",
            body={"sound": sound_id},
            success_message="Boombox activated.",
        )
    )


@security_group.command("pin-reset")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def pin_reset_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Reset PIN to Drive."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "reset_pin_to_drive_pin",
            "security.pin-reset",
            success_message="PIN to Drive reset.",
        )
    )


@security_group.command("pin-clear-admin")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def pin_clear_admin_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Admin clear PIN to Drive (fleet manager only)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "clear_pin_to_drive_admin",
            "security.pin-clear-admin",
            success_message="PIN cleared (admin).",
        )
    )


@security_group.command("speed-clear")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--pin", required=True, help="Speed limit PIN")
@global_options
def speed_clear_cmd(app_ctx: AppContext, vin_positional: str | None, pin: str) -> None:
    """Clear speed limit PIN."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "speed_limit_clear_pin",
            "security.speed-clear",
            body={"pin": pin},
            success_message="Speed limit PIN cleared.",
        )
    )


@security_group.command("speed-clear-admin")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def speed_clear_admin_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Admin clear speed limit PIN (fleet manager only)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "speed_limit_clear_pin_admin",
            "security.speed-clear-admin",
            success_message="Speed limit PIN cleared (admin).",
        )
    )


@security_group.command("speed-limit")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.option("--activate", "pin_activate", default=None, help="Activate speed limit with PIN")
@click.option(
    "--deactivate", "pin_deactivate", default=None, help="Deactivate speed limit with PIN"
)
@click.option("--set", "limit_mph", type=float, default=None, help="Set speed limit in MPH")
@global_options
def speed_limit_cmd(
    app_ctx: AppContext,
    vin_positional: str | None,
    pin_activate: str | None,
    pin_deactivate: str | None,
    limit_mph: float | None,
) -> None:
    """Manage speed limit mode (--activate PIN, --deactivate PIN, or --set MPH)."""
    run_async(_cmd_speed_limit(app_ctx, vin_positional, pin_activate, pin_deactivate, limit_mph))


async def _cmd_speed_limit(
    app_ctx: AppContext,
    vin_positional: str | None,
    pin_activate: str | None,
    pin_deactivate: str | None,
    limit_mph: float | None,
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)

    provided = sum(x is not None for x in (pin_activate, pin_deactivate, limit_mph))
    if provided != 1:
        raise ConfigError("Specify exactly one of --activate PIN, --deactivate PIN, or --set MPH.")

    client, vehicle_api, cmd_api = get_command_api(app_ctx)
    try:
        if pin_activate is not None:
            result = await auto_wake(
                formatter,
                vehicle_api,
                vin,
                lambda: cmd_api.speed_limit_activate(vin, pin=pin_activate),
                auto=app_ctx.auto_wake,
            )
            cmd_name = "security.speed-limit.activate"
        elif pin_deactivate is not None:
            result = await auto_wake(
                formatter,
                vehicle_api,
                vin,
                lambda: cmd_api.speed_limit_deactivate(vin, pin=pin_deactivate),
                auto=app_ctx.auto_wake,
            )
            cmd_name = "security.speed-limit.deactivate"
        else:
            assert limit_mph is not None
            result = await auto_wake(
                formatter,
                vehicle_api,
                vin,
                lambda: cmd_api.speed_limit_set_limit(vin, limit_mph=limit_mph),
                auto=app_ctx.auto_wake,
            )
            cmd_name = "security.speed-limit.set"
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command=cmd_name)
    else:
        msg = result.response.reason or "Speed limit updated."
        formatter.rich.command_result(result.response.result, msg)
