"""CLI commands for vehicle operations (list, info, data, location, wake)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from tescmd._internal.vin import resolve_vin
from tescmd.api.client import TeslaFleetClient
from tescmd.api.errors import ConfigError, VehicleAsleepError
from tescmd.api.vehicle import VehicleAPI
from tescmd.auth.token_store import TokenStore
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    import argparse

    from tescmd.output.formatter import OutputFormatter


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``vehicle`` command group and its sub-commands."""
    vehicle_parser = subparsers.add_parser("vehicle", help="Vehicle commands")
    vehicle_sub = vehicle_parser.add_subparsers(dest="subcommand")

    # -- list ----------------------------------------------------------------
    list_p = vehicle_sub.add_parser("list", help="List all vehicles")
    list_p.set_defaults(func=cmd_list)

    # -- info ----------------------------------------------------------------
    info_p = vehicle_sub.add_parser("info", help="Show vehicle info")
    info_p.add_argument("vin_positional", nargs="?", default=None, help="Vehicle VIN")
    info_p.set_defaults(func=cmd_info)

    # -- data ----------------------------------------------------------------
    data_p = vehicle_sub.add_parser("data", help="Show full vehicle data")
    data_p.add_argument("vin_positional", nargs="?", default=None, help="Vehicle VIN")
    data_p.add_argument("--endpoints", default=None, help="Comma-separated endpoint filter")
    data_p.set_defaults(func=cmd_data)

    # -- location ------------------------------------------------------------
    loc_p = vehicle_sub.add_parser("location", help="Show vehicle location")
    loc_p.add_argument("vin_positional", nargs="?", default=None, help="Vehicle VIN")
    loc_p.set_defaults(func=cmd_location)

    # -- wake ----------------------------------------------------------------
    wake_p = vehicle_sub.add_parser("wake", help="Wake up the vehicle")
    wake_p.add_argument("vin_positional", nargs="?", default=None, help="Vehicle VIN")
    wake_p.add_argument("--wait", action="store_true", help="Wait for vehicle to come online")
    wake_p.add_argument(
        "--timeout", type=int, default=30, help="Timeout in seconds when using --wait"
    )
    wake_p.set_defaults(func=cmd_wake)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_client_and_api(args: argparse.Namespace) -> tuple[TeslaFleetClient, VehicleAPI]:
    """Build a TeslaFleetClient + VehicleAPI from settings / token store."""
    settings = AppSettings()

    # Access token: env var takes precedence, then keyring
    access_token = settings.access_token
    if not access_token:
        store = TokenStore(profile=getattr(args, "profile", "default"))
        access_token = store.access_token

    if not access_token:
        raise ConfigError(
            "No access token found. Run 'tescmd auth login' or set TESLA_ACCESS_TOKEN."
        )

    region = getattr(args, "region", None) or settings.region
    client = TeslaFleetClient(access_token=access_token, region=region)
    return client, VehicleAPI(client)


def _require_vin(args: argparse.Namespace) -> str:
    """Resolve VIN or raise ConfigError."""
    vin = resolve_vin(args)
    if not vin:
        raise ConfigError(
            "No VIN specified. Pass it as a positional argument, use --vin, or set TESLA_VIN."
        )
    return vin


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_list(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """List all vehicles on the account."""
    client, api = _get_client_and_api(args)
    try:
        vehicles = await api.list_vehicles()
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vehicles, command="vehicle.list")
    else:
        formatter.rich.vehicle_list(vehicles)


async def cmd_info(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Show vehicle info (full vehicle_data)."""
    vin = _require_vin(args)
    client, api = _get_client_and_api(args)
    try:
        vdata = await api.get_vehicle_data(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vdata, command="vehicle.info")
    else:
        formatter.rich.vehicle_data(vdata)


async def cmd_data(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Show vehicle data with optional endpoint filtering."""
    vin = _require_vin(args)
    endpoints: list[str] | None = None
    if args.endpoints:
        endpoints = [e.strip() for e in args.endpoints.split(",")]

    client, api = _get_client_and_api(args)
    try:
        vdata = await api.get_vehicle_data(vin, endpoints=endpoints)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vdata, command="vehicle.data")
    else:
        formatter.rich.vehicle_data(vdata)


async def cmd_location(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Show the vehicle's current location."""
    vin = _require_vin(args)
    client, api = _get_client_and_api(args)
    try:
        vdata = await api.get_vehicle_data(vin, endpoints=["drive_state"])
    finally:
        await client.close()

    if formatter.format == "json":
        ds = vdata.drive_state
        formatter.output(
            ds.model_dump(exclude_none=True) if ds else {},
            command="vehicle.location",
        )
    else:
        if vdata.drive_state:
            formatter.rich.location(vdata.drive_state)
        else:
            formatter.rich.info("No drive state data available.")


async def cmd_wake(args: argparse.Namespace, formatter: OutputFormatter) -> None:
    """Wake the vehicle, optionally waiting for it to come online."""
    vin = _require_vin(args)
    client, api = _get_client_and_api(args)
    try:
        vehicle = await api.wake(vin)

        if args.wait and vehicle.state != "online":
            timeout: int = args.timeout
            elapsed = 0
            while elapsed < timeout and vehicle.state != "online":
                await asyncio.sleep(2)
                elapsed += 2
                with contextlib.suppress(VehicleAsleepError):
                    vehicle = await api.wake(vin)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(vehicle, command="vehicle.wake")
    else:
        state = vehicle.state
        style = "green" if state == "online" else "yellow"
        formatter.rich.info(f"Vehicle state: [{style}]{state}[/{style}]")
