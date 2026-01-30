"""CLI commands for vehicle sharing (drivers and invites)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import get_sharing_api, require_vin
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

sharing_group = click.Group("sharing", help="Vehicle sharing commands")


@sharing_group.command("add-driver")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("email")
@global_options
def add_driver_cmd(app_ctx: AppContext, vin_positional: str | None, email: str) -> None:
    """Add a driver by EMAIL."""
    run_async(_cmd_add_driver(app_ctx, vin_positional, email))


async def _cmd_add_driver(app_ctx: AppContext, vin_positional: str | None, email: str) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_sharing_api(app_ctx)
    try:
        result = await api.add_driver(vin, email=email)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="sharing.add-driver")
    else:
        formatter.rich.info(f"Driver invite sent to {email}")


@sharing_group.command("remove-driver")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("share_user_id", type=int)
@global_options
def remove_driver_cmd(app_ctx: AppContext, vin_positional: str | None, share_user_id: int) -> None:
    """Remove a driver by SHARE_USER_ID."""
    run_async(_cmd_remove_driver(app_ctx, vin_positional, share_user_id))


async def _cmd_remove_driver(
    app_ctx: AppContext, vin_positional: str | None, share_user_id: int
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_sharing_api(app_ctx)
    try:
        result = await api.remove_driver(vin, share_user_id=share_user_id)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="sharing.remove-driver")
    else:
        formatter.rich.info("Driver removed")


@sharing_group.command("create-invite")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def create_invite_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Create a vehicle share invite."""
    run_async(_cmd_create_invite(app_ctx, vin_positional))


async def _cmd_create_invite(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_sharing_api(app_ctx)
    try:
        result = await api.create_invite(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="sharing.create-invite")
    else:
        code = result.code or ""
        formatter.rich.info(f"Invite created: {code}" if code else "Invite created")


@sharing_group.command("redeem-invite")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("code")
@global_options
def redeem_invite_cmd(app_ctx: AppContext, vin_positional: str | None, code: str) -> None:
    """Redeem a vehicle share invite CODE."""
    run_async(_cmd_redeem_invite(app_ctx, vin_positional, code))


async def _cmd_redeem_invite(app_ctx: AppContext, vin_positional: str | None, code: str) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_sharing_api(app_ctx)
    try:
        result = await api.redeem_invite(vin, code=code)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="sharing.redeem-invite")
    else:
        formatter.rich.info("Invite redeemed")


@sharing_group.command("revoke-invite")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("invite_id")
@global_options
def revoke_invite_cmd(app_ctx: AppContext, vin_positional: str | None, invite_id: str) -> None:
    """Revoke a vehicle share invite by ID."""
    run_async(_cmd_revoke_invite(app_ctx, vin_positional, invite_id))


async def _cmd_revoke_invite(
    app_ctx: AppContext, vin_positional: str | None, invite_id: str
) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_sharing_api(app_ctx)
    try:
        result = await api.revoke_invite(vin, invite_id=invite_id)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="sharing.revoke-invite")
    else:
        formatter.rich.info("Invite revoked")


@sharing_group.command("list-invites")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def list_invites_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """List active vehicle share invites."""
    run_async(_cmd_list_invites(app_ctx, vin_positional))


async def _cmd_list_invites(app_ctx: AppContext, vin_positional: str | None) -> None:
    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, api = get_sharing_api(app_ctx)
    try:
        invites = await api.list_invites(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(invites, command="sharing.list-invites")
    else:
        if invites:
            for inv in invites:
                formatter.rich.info(f"  ID: {inv.id or ''}  Code: {inv.code or ''}")
        else:
            formatter.rich.info("[dim]No active invites.[/dim]")
