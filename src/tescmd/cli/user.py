"""CLI commands for user account operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import TTL_DEFAULT, TTL_STATIC, cached_api_call, get_user_api
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

user_group = click.Group("user", help="User account commands")


@user_group.command("me")
@global_options
def me_cmd(app_ctx: AppContext) -> None:
    """Show account information."""
    run_async(_cmd_me(app_ctx))


async def _cmd_me(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_user_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="user.me",
            fetch=lambda: api.me(),
            ttl=TTL_STATIC,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="user.me")
    else:
        formatter.rich.user_info(data)


@user_group.command("region")
@global_options
def region_cmd(app_ctx: AppContext) -> None:
    """Show regional Fleet API endpoint."""
    run_async(_cmd_region(app_ctx))


async def _cmd_region(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_user_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="user.region",
            fetch=lambda: api.region(),
            ttl=TTL_STATIC,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="user.region")
    else:
        formatter.rich.user_region(data)


@user_group.command("orders")
@global_options
def orders_cmd(app_ctx: AppContext) -> None:
    """Show vehicle orders."""
    run_async(_cmd_orders(app_ctx))


async def _cmd_orders(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_user_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="user.orders",
            fetch=lambda: api.orders(),
            ttl=TTL_DEFAULT,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="user.orders")
    else:
        if data:
            for order in data:
                if isinstance(order, dict):
                    oid = order.get("order_id") or "?"
                    model = order.get("model") or ""
                    status = order.get("status") or ""
                else:
                    oid = order.order_id or "?"
                    model = order.model or ""
                    status = order.status or ""
                formatter.rich.info(f"  {oid}: {model} [{status}]")
        else:
            formatter.rich.info("[dim]No orders found.[/dim]")


@user_group.command("features")
@global_options
def features_cmd(app_ctx: AppContext) -> None:
    """Show feature flags."""
    run_async(_cmd_features(app_ctx))


async def _cmd_features(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    client, api = get_user_api(app_ctx)
    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="user.features",
            fetch=lambda: api.feature_config(),
            ttl=TTL_STATIC,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="user.features")
    else:
        dumped = data.model_dump(exclude_none=True) if hasattr(data, "model_dump") else data
        if dumped:
            for key, val in sorted(dumped.items()):
                formatter.rich.info(f"  {key}: {val}")
        else:
            formatter.rich.info("[dim]No feature flags available.[/dim]")
