"""High-level Vehicle API built on top of TeslaFleetClient."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tescmd.models.sharing import ShareDriverInfo
from tescmd.models.vehicle import NearbyChargingSites, Vehicle, VehicleData

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

    async def get_vehicle(self, vin: str) -> Vehicle:
        """Fetch a single vehicle by VIN."""
        data = await self._client.get(f"/api/1/vehicles/{vin}")
        return Vehicle.model_validate(data["response"])

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

    async def mobile_enabled(self, vin: str) -> bool:
        """Check if mobile access is enabled for the vehicle."""
        data = await self._client.get(f"/api/1/vehicles/{vin}/mobile_enabled")
        return bool(data.get("response", False))

    async def nearby_charging_sites(self, vin: str) -> NearbyChargingSites:
        """Fetch nearby Superchargers and destination chargers."""
        data = await self._client.get(f"/api/1/vehicles/{vin}/nearby_charging_sites")
        return NearbyChargingSites.model_validate(data.get("response", {}))

    async def recent_alerts(self, vin: str) -> list[dict[str, Any]]:
        """Fetch recent vehicle alerts."""
        data = await self._client.get(f"/api/1/vehicles/{vin}/recent_alerts")
        result: list[dict[str, Any]] = data.get("response", [])
        return result

    async def release_notes(self, vin: str) -> dict[str, Any]:
        """Fetch firmware release notes."""
        data = await self._client.get(f"/api/1/vehicles/{vin}/release_notes")
        result: dict[str, Any] = data.get("response", {})
        return result

    async def service_data(self, vin: str) -> dict[str, Any]:
        """Fetch vehicle service data."""
        data = await self._client.get(f"/api/1/vehicles/{vin}/service_data")
        result: dict[str, Any] = data.get("response", {})
        return result

    async def list_drivers(self, vin: str) -> list[ShareDriverInfo]:
        """List drivers associated with the vehicle."""
        data = await self._client.get(f"/api/1/vehicles/{vin}/drivers")
        raw_list: list[dict[str, Any]] = data.get("response", [])
        return [ShareDriverInfo.model_validate(d) for d in raw_list]
