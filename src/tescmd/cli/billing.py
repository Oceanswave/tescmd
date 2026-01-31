"""CLI commands for Supercharger billing (history, sessions, invoices)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import TTL_DEFAULT, cached_api_call, get_billing_api
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

billing_group = click.Group("billing", help="Supercharger billing history and invoices")


# ---------------------------------------------------------------------------
# billing history
# ---------------------------------------------------------------------------


@billing_group.command("history")
@click.option("--vin", "vin_filter", default=None, help="Filter by vehicle VIN")
@click.option("--start", "start_time", default=None, help="Start time (ISO-8601)")
@click.option("--end", "end_time", default=None, help="End time (ISO-8601)")
@click.option("--page", type=int, default=None, help="Page number (0-based)")
@click.option("--page-size", type=int, default=None, help="Results per page")
@global_options
def history_cmd(
    app_ctx: AppContext,
    vin_filter: str | None,
    start_time: str | None,
    end_time: str | None,
    page: int | None,
    page_size: int | None,
) -> None:
    """Show Supercharger charging history."""
    run_async(_cmd_history(app_ctx, vin_filter, start_time, end_time, page, page_size))


async def _cmd_history(
    app_ctx: AppContext,
    vin_filter: str | None,
    start_time: str | None,
    end_time: str | None,
    page: int | None,
    page_size: int | None,
) -> None:
    formatter = app_ctx.formatter
    client, api = get_billing_api(app_ctx)

    # Build params dict for cache key differentiation
    cache_params: dict[str, str] = {}
    if vin_filter:
        cache_params["vin"] = vin_filter
    if start_time:
        cache_params["start"] = start_time
    if end_time:
        cache_params["end"] = end_time
    if page is not None:
        cache_params["page"] = str(page)
    if page_size is not None:
        cache_params["page_size"] = str(page_size)

    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="billing.history",
            fetch=lambda: api.charging_history(
                vin=vin_filter,
                start_time=start_time,
                end_time=end_time,
                page_no=page,
                page_size=page_size,
            ),
            ttl=TTL_DEFAULT,
            params=cache_params or None,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="billing.history")
    else:
        _display_charging_history(formatter, data)


def _display_charging_history(formatter: object, data: dict) -> None:  # type: ignore[type-arg]
    """Render charging history in Rich format."""
    from tescmd.output.formatter import OutputFormatter

    assert isinstance(formatter, OutputFormatter)
    records = data.get("data", data.get("chargingHistoryDetailList", []))
    if not records:
        formatter.rich.info("[dim]No charging history records found.[/dim]")
        return

    from rich.table import Table

    table = Table(title="Charging History", show_lines=False)
    table.add_column("Date", style="cyan")
    table.add_column("VIN")
    table.add_column("Location")
    table.add_column("Energy (kWh)", justify="right")
    table.add_column("Cost", justify="right")

    for rec in records:
        date = str(rec.get("sessionStartDateTime", rec.get("chargeStartDateTime", "—")))
        vin = str(rec.get("vin", "—"))
        location = str(rec.get("siteLocationName", rec.get("chargeSessionTitle", "—")))
        energy = str(rec.get("chargeSessionEnergyKwh", rec.get("energyAdded", "—")))
        fees = rec.get("fees", [])
        cost = "—"
        if fees and isinstance(fees, list):
            total = sum(float(f.get("totalDue", 0)) for f in fees if isinstance(f, dict))
            currency = fees[0].get("currencyCode", "") if fees else ""
            cost = f"{total:.2f} {currency}".strip()
        elif "billingTotal" in rec:
            cost = str(rec["billingTotal"])
        table.add_row(date[:16], vin, location[:30], energy, cost)

    formatter.rich._con.print(table)


# ---------------------------------------------------------------------------
# billing sessions (business accounts)
# ---------------------------------------------------------------------------


@billing_group.command("sessions")
@click.option("--vin", "vin_filter", default=None, help="Filter by vehicle VIN")
@click.option("--from", "date_from", default=None, help="Start date (ISO-8601)")
@click.option("--to", "date_to", default=None, help="End date (ISO-8601)")
@click.option("--limit", type=int, default=None, help="Max results")
@click.option("--offset", type=int, default=None, help="Pagination offset")
@global_options
def sessions_cmd(
    app_ctx: AppContext,
    vin_filter: str | None,
    date_from: str | None,
    date_to: str | None,
    limit: int | None,
    offset: int | None,
) -> None:
    """Show charging sessions (business accounts only)."""
    run_async(_cmd_sessions(app_ctx, vin_filter, date_from, date_to, limit, offset))


async def _cmd_sessions(
    app_ctx: AppContext,
    vin_filter: str | None,
    date_from: str | None,
    date_to: str | None,
    limit: int | None,
    offset: int | None,
) -> None:
    formatter = app_ctx.formatter
    client, api = get_billing_api(app_ctx)

    cache_params: dict[str, str] = {}
    if vin_filter:
        cache_params["vin"] = vin_filter
    if date_from:
        cache_params["from"] = date_from
    if date_to:
        cache_params["to"] = date_to
    if limit is not None:
        cache_params["limit"] = str(limit)
    if offset is not None:
        cache_params["offset"] = str(offset)

    try:
        data = await cached_api_call(
            app_ctx,
            scope="account",
            identifier="global",
            endpoint="billing.sessions",
            fetch=lambda: api.charging_sessions(
                vin=vin_filter,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            ),
            ttl=TTL_DEFAULT,
            params=cache_params or None,
        )
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="billing.sessions")
    else:
        sessions = data if isinstance(data, list) else data.get("data", [])
        if not sessions:
            formatter.rich.info("[dim]No charging sessions found.[/dim]")
        else:
            formatter.rich.info(f"Found {len(sessions)} charging session(s).")
            for s in sessions:
                formatter.rich.info(f"  {s}")


# ---------------------------------------------------------------------------
# billing invoice
# ---------------------------------------------------------------------------


@billing_group.command("invoice")
@click.argument("invoice_id")
@click.option("--output", "-o", "output_path", default=None, help="Save PDF to file path")
@global_options
def invoice_cmd(
    app_ctx: AppContext,
    invoice_id: str,
    output_path: str | None,
) -> None:
    """Download a charging invoice by ID."""
    run_async(_cmd_invoice(app_ctx, invoice_id, output_path))


async def _cmd_invoice(
    app_ctx: AppContext,
    invoice_id: str,
    output_path: str | None,
) -> None:
    formatter = app_ctx.formatter
    client, api = get_billing_api(app_ctx)
    try:
        data = await api.charging_invoice(invoice_id)
    finally:
        await client.close()

    if formatter.format == "json":
        formatter.output(data, command="billing.invoice")
    else:
        formatter.rich._dict_table(f"Invoice {invoice_id}", data)
