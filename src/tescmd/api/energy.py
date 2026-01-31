"""Energy site API — wraps /api/1/energy_sites/{site_id} endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tescmd.models.energy import CalendarHistory, LiveStatus, SiteInfo

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class EnergyAPI:
    """Energy site operations (Powerwall, Solar, etc.)."""

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def list_products(self) -> list[dict[str, Any]]:
        """Return all energy products on the account."""
        data = await self._client.get("/api/1/products")
        result: list[dict[str, Any]] = data.get("response", [])
        return result

    async def live_status(self, site_id: int) -> LiveStatus:
        """Fetch real-time power flow for a site."""
        data = await self._client.get(f"/api/1/energy_sites/{site_id}/live_status")
        return LiveStatus.model_validate(data.get("response", {}))

    async def site_info(self, site_id: int) -> SiteInfo:
        """Fetch site configuration and metadata."""
        data = await self._client.get(f"/api/1/energy_sites/{site_id}/site_info")
        return SiteInfo.model_validate(data.get("response", {}))

    async def set_backup_reserve(self, site_id: int, *, percent: int) -> dict[str, Any]:
        """Set the backup reserve percentage."""
        data = await self._client.post(
            f"/api/1/energy_sites/{site_id}/backup",
            json={"backup_reserve_percent": percent},
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def set_operation_mode(self, site_id: int, *, mode: str) -> dict[str, Any]:
        """Set the site operation mode (self_consumption, backup, autonomous)."""
        data = await self._client.post(
            f"/api/1/energy_sites/{site_id}/operation",
            json={"default_real_mode": mode},
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def set_storm_mode(self, site_id: int, *, enabled: bool) -> dict[str, Any]:
        """Enable or disable storm watch."""
        data = await self._client.post(
            f"/api/1/energy_sites/{site_id}/storm_mode",
            json={"enabled": enabled},
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def time_of_use_settings(
        self, site_id: int, *, settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Set time-of-use schedule."""
        data = await self._client.post(
            f"/api/1/energy_sites/{site_id}/time_of_use_settings",
            json={"tou_settings": settings},
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def charging_history(self, site_id: int) -> CalendarHistory:
        """Fetch charging history for a site (wall connector telemetry)."""
        data = await self._client.get(
            f"/api/1/energy_sites/{site_id}/telemetry_history",
            params={"kind": "charge"},
        )
        return CalendarHistory.model_validate(data.get("response", {}))

    async def off_grid_vehicle_charging_reserve(
        self, site_id: int, *, reserve: int
    ) -> dict[str, Any]:
        """Set off-grid EV charging reserve percentage."""
        data = await self._client.post(
            f"/api/1/energy_sites/{site_id}/off_grid_vehicle_charging_reserve",
            json={"off_grid_vehicle_charging_reserve_percent": reserve},
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def grid_import_export(self, site_id: int, *, config: dict[str, Any]) -> dict[str, Any]:
        """Set grid import/export configuration."""
        data = await self._client.post(
            f"/api/1/energy_sites/{site_id}/grid_import_export",
            json=config,
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def telemetry_history(
        self,
        site_id: int,
        *,
        kind: str = "charge",
        start_date: str | None = None,
        end_date: str | None = None,
        time_zone: str | None = None,
    ) -> CalendarHistory:
        """Fetch telemetry-based charge history for a site."""
        params: dict[str, str] = {"kind": kind}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if time_zone:
            params["time_zone"] = time_zone
        data = await self._client.get(
            f"/api/1/energy_sites/{site_id}/telemetry_history",
            params=params,
        )
        return CalendarHistory.model_validate(data.get("response", {}))

    async def calendar_history(
        self,
        site_id: int,
        *,
        kind: str = "energy",
        period: str = "day",
        start_date: str | None = None,
        end_date: str | None = None,
        time_zone: str | None = None,
    ) -> CalendarHistory:
        """Fetch calendar-based history for a site."""
        params: dict[str, str] = {"kind": kind, "period": period}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if time_zone:
            params["time_zone"] = time_zone
        data = await self._client.get(
            f"/api/1/energy_sites/{site_id}/calendar_history",
            params=params,
        )
        return CalendarHistory.model_validate(data.get("response", {}))
