"""Tests for tescmd.api.client — TeslaFleetClient."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tescmd.api.client import TeslaFleetClient
from tescmd.api.errors import (
    RateLimitError,
    VehicleAsleepError,
)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


@pytest.fixture
def client() -> TeslaFleetClient:
    return TeslaFleetClient(access_token="tok123", region="na")


class TestGetSuccess:
    @pytest.mark.asyncio
    async def test_get_success(self, httpx_mock: HTTPXMock, client: TeslaFleetClient) -> None:
        payload = {"response": [{"vin": "5YJ3E1EA1NF000001", "display_name": "My Model 3"}]}
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            json=payload,
        )
        result = await client.get("/api/1/vehicles")
        assert result == payload


class TestPostSuccess:
    @pytest.mark.asyncio
    async def test_post_success(self, httpx_mock: HTTPXMock, client: TeslaFleetClient) -> None:
        payload = {"response": {"result": True, "reason": ""}}
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/123/command/door_lock",
            json=payload,
        )
        result = await client.post("/api/1/vehicles/123/command/door_lock")
        assert result["response"]["result"] is True


class TestAuthHeaderSent:
    @pytest.mark.asyncio
    async def test_auth_header_sent(self, httpx_mock: HTTPXMock, client: TeslaFleetClient) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            json={"response": []},
        )
        await client.get("/api/1/vehicles")
        request = httpx_mock.get_requests()[0]
        assert request.headers["authorization"] == "Bearer tok123"


class TestRateLimitRaises:
    @pytest.mark.asyncio
    async def test_rate_limit_raises(
        self, httpx_mock: HTTPXMock, client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            status_code=429,
            headers={"retry-after": "30"},
        )
        with pytest.raises(RateLimitError) as exc_info:
            await client.get("/api/1/vehicles")
        assert exc_info.value.retry_after == 30
        assert exc_info.value.status_code == 429


class TestVehicleAsleepRaises:
    @pytest.mark.asyncio
    async def test_vehicle_asleep_raises(
        self, httpx_mock: HTTPXMock, client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/123/data",
            status_code=408,
        )
        with pytest.raises(VehicleAsleepError) as exc_info:
            await client.get("/api/1/vehicles/123/data")
        assert exc_info.value.status_code == 408


class TestRegionBaseUrl:
    def test_region_base_url(self) -> None:
        eu_client = TeslaFleetClient(access_token="tok", region="eu")
        assert "eu" in str(eu_client._client.base_url)
