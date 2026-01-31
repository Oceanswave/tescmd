"""Charging history API — wraps /api/1/dx/charging endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class ChargingAPI:
    """Charging history and invoice operations (composition over TeslaFleetClient)."""

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def charging_history(
        self,
        *,
        vin: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page_no: int | None = None,
        page_size: int | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> dict[str, Any]:
        """Fetch paginated Supercharger charging history.

        Args:
            vin: Filter by vehicle VIN.
            start_time: ISO-8601 start time filter.
            end_time: ISO-8601 end time filter.
            page_no: Page number (0-based).
            page_size: Results per page.
            sort_by: Field to sort by.
            sort_order: Sort order (ASC or DESC).
        """
        params: dict[str, str] = {}
        if vin is not None:
            params["vin"] = vin
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if page_no is not None:
            params["pageNo"] = str(page_no)
        if page_size is not None:
            params["pageSize"] = str(page_size)
        if sort_by is not None:
            params["sortBy"] = sort_by
        if sort_order is not None:
            params["sortOrder"] = sort_order
        data = await self._client.get("/api/1/dx/charging/history", params=params)
        result: dict[str, Any] = data.get("response", {})
        return result

    async def charging_sessions(
        self,
        *,
        vin: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """Fetch charging sessions (business accounts only).

        Args:
            vin: Filter by vehicle VIN.
            date_from: ISO-8601 start date.
            date_to: ISO-8601 end date.
            limit: Max results to return.
            offset: Pagination offset.
        """
        params: dict[str, str] = {}
        if vin is not None:
            params["vin"] = vin
        if date_from is not None:
            params["date_from"] = date_from
        if date_to is not None:
            params["date_to"] = date_to
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        data = await self._client.get("/api/1/dx/charging/sessions", params=params)
        result: dict[str, Any] = data.get("response", {})
        return result

    async def charging_invoice(self, invoice_id: str) -> dict[str, Any]:
        """Download a charging invoice.

        Args:
            invoice_id: The invoice identifier.

        Returns:
            Invoice response data (may contain a download URL or inline content).
        """
        data = await self._client.get(f"/api/1/dx/charging/invoice/{invoice_id}")
        result: dict[str, Any] = data.get("response", data) if isinstance(data, dict) else {}
        return result
