"""User account API — wraps /api/1/users endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tescmd.models.user import FeatureConfig, UserInfo, UserRegion, VehicleOrder

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class UserAPI:
    """User account operations (no VIN required)."""

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def me(self) -> UserInfo:
        """Fetch the current user's profile."""
        data = await self._client.get("/api/1/users/me")
        return UserInfo.model_validate(data.get("response", {}))

    async def region(self) -> UserRegion:
        """Fetch the user's regional Fleet API endpoint."""
        data = await self._client.get("/api/1/users/region")
        return UserRegion.model_validate(data.get("response", {}))

    async def orders(self) -> list[VehicleOrder]:
        """Fetch the user's vehicle orders."""
        data = await self._client.get("/api/1/users/orders")
        raw_list: list[dict[str, Any]] = data.get("response", [])
        return [VehicleOrder.model_validate(o) for o in raw_list]

    async def feature_config(self) -> FeatureConfig:
        """Fetch the user's feature flags."""
        data = await self._client.get("/api/1/users/feature_config")
        return FeatureConfig.model_validate(data.get("response", {}))
