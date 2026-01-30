"""CLI commands for raw Fleet API access (power-user escape hatch)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import get_client
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

raw_group = click.Group("raw", help="Raw Fleet API access")


@raw_group.command("get")
@click.argument("path")
@click.option("--params", default=None, help="Query parameters as JSON string")
@global_options
def get_cmd(app_ctx: AppContext, path: str, params: str | None) -> None:
    """Send a raw GET request to PATH.

    Example: tescmd raw get /api/1/vehicles
    """
    run_async(_cmd_get(app_ctx, path, params))


async def _cmd_get(app_ctx: AppContext, path: str, params_json: str | None) -> None:
    formatter = app_ctx.formatter
    client = get_client(app_ctx)
    try:
        kwargs: dict[str, object] = {}
        if params_json:
            kwargs["params"] = json.loads(params_json)
        data = await client.get(path, **kwargs)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="raw.get")
    else:
        formatter.rich.info(json.dumps(data, indent=2, default=str))


@raw_group.command("post")
@click.argument("path")
@click.option("--body", default=None, help="Request body as JSON string")
@global_options
def post_cmd(app_ctx: AppContext, path: str, body: str | None) -> None:
    """Send a raw POST request to PATH.

    Example: tescmd raw post /api/1/vehicles/VIN/command/flash_lights
    """
    run_async(_cmd_post(app_ctx, path, body))


async def _cmd_post(app_ctx: AppContext, path: str, body_json: str | None) -> None:
    formatter = app_ctx.formatter
    client = get_client(app_ctx)
    try:
        kwargs: dict[str, object] = {}
        if body_json:
            kwargs["json"] = json.loads(body_json)
        data = await client.post(path, **kwargs)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="raw.post")
    else:
        formatter.rich.info(json.dumps(data, indent=2, default=str))
