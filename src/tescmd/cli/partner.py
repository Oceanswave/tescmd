"""CLI commands for partner account endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import TTL_SLOW, TTL_STATIC, cached_api_call, get_partner_api
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

partner_group = click.Group(
    "partner", help="Partner account endpoints (require client credentials)"
)


@partner_group.command("public-key")
@click.option("--domain", required=True, help="Domain to look up")
@global_options
def public_key_cmd(app_ctx: AppContext, domain: str) -> None:
    """Get the public key registered for DOMAIN."""
    run_async(_cmd_public_key(app_ctx, domain))


async def _cmd_public_key(app_ctx: AppContext, domain: str) -> None:
    formatter = app_ctx.formatter
    client, api = await get_partner_api(app_ctx)
    try:
        result = await cached_api_call(
            app_ctx,
            scope="partner",
            identifier=domain,
            endpoint="partner.public-key",
            fetch=lambda: api.public_key(domain=domain),
            ttl=TTL_STATIC,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="partner.public-key")
    else:
        formatter.rich._dict_table("Public Key", result)


@partner_group.command("telemetry-error-vins")
@global_options
def telemetry_error_vins_cmd(app_ctx: AppContext) -> None:
    """List VINs with recent fleet telemetry errors."""
    run_async(_cmd_telemetry_error_vins(app_ctx))


async def _cmd_telemetry_error_vins(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = await get_partner_api(app_ctx)
    try:
        result = await cached_api_call(
            app_ctx,
            scope="partner",
            identifier="global",
            endpoint="partner.telemetry-error-vins",
            fetch=lambda: api.fleet_telemetry_error_vins(),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="partner.telemetry-error-vins")
    else:
        if result:
            formatter.rich.info("VINs with telemetry errors:")
            for vin in result:
                formatter.rich.info(f"  {vin}")
        else:
            formatter.rich.info("[dim]No VINs with telemetry errors.[/dim]")


@partner_group.command("telemetry-errors")
@global_options
def telemetry_errors_cmd(app_ctx: AppContext) -> None:
    """Get recent fleet telemetry errors across all vehicles."""
    run_async(_cmd_telemetry_errors(app_ctx))


async def _cmd_telemetry_errors(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = await get_partner_api(app_ctx)
    try:
        result = await cached_api_call(
            app_ctx,
            scope="partner",
            identifier="global",
            endpoint="partner.telemetry-errors",
            fetch=lambda: api.fleet_telemetry_errors(),
            ttl=TTL_SLOW,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(result, command="partner.telemetry-errors")
    else:
        if result:
            for err in result:
                formatter.rich._dict_table("Telemetry Error", err)
        else:
            formatter.rich.info("[dim]No recent telemetry errors.[/dim]")
