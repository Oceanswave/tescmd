"""High-level Vehicle API built on top of TeslaFleetClient."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tescmd.models.vehicle import Vehicle, VehicleData

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class VehicleAPI:
    """Vehicle-related API operations (composition over TeslaFleetClient)."""

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def list_vehicles(self) -> list[Vehicle]:
        """Return all vehicles associated with the account."""
        data = await self._client.get("/api/1/vehicles")
        raw_list: list[dict[str, object]] = data.get("response", [])
        return [Vehicle.model_validate(v) for v in raw_list]

    async def get_vehicle_data(
        self,
        vin: str,
        *,
        endpoints: list[str] | None = None,
    ) -> VehicleData:
        """Fetch full vehicle data, optionally filtered to *endpoints*."""
        path = f"/api/1/vehicles/{vin}/vehicle_data"
        params: dict[str, str] = {}
        if endpoints:
            params["endpoints"] = ";".join(endpoints)
        data = await self._client.get(path, params=params)
        return VehicleData.model_validate(data["response"])

    async def wake(self, vin: str) -> Vehicle:
        """Send a wake-up command and return the vehicle state."""
        data = await self._client.post(f"/api/1/vehicles/{vin}/wake_up")
        return Vehicle.model_validate(data["response"])
