"""Tests for tescmd.api.client — TeslaFleetClient."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from tescmd.api.client import _RATE_LIMIT_MAX_RETRIES, TeslaFleetClient
from tescmd.api.errors import (
    AuthError,
    MissingScopesError,
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


class TestDeleteMethod:
    @pytest.mark.asyncio
    async def test_delete_success(self, httpx_mock: HTTPXMock, client: TeslaFleetClient) -> None:
        payload = {"response": {"deleted": True}}
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/123/fleet_telemetry_config",
            json=payload,
            method="DELETE",
        )
        result = await client.delete("/api/1/vehicles/123/fleet_telemetry_config")
        assert result["response"]["deleted"] is True


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
        # Provide enough 429 responses to exhaust all retries.
        # Use retry-after: 0 so tests don't sleep.
        for _ in range(_RATE_LIMIT_MAX_RETRIES + 1):
            httpx_mock.add_response(
                url=f"{FLEET_BASE}/api/1/vehicles",
                status_code=429,
                headers={"retry-after": "0"},
            )
        with pytest.raises(RateLimitError) as exc_info:
            await client.get("/api/1/vehicles")
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


class TestRateLimitRetriesThenSucceeds:
    @pytest.mark.asyncio
    async def test_rate_limit_retries_then_succeeds(self, httpx_mock: HTTPXMock) -> None:
        client = TeslaFleetClient(access_token="tok123", region="na")
        # First response: 429 with retry-after: 0 (no real delay)
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            status_code=429,
            headers={"retry-after": "0"},
        )
        # Second response: success
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            json={"response": []},
        )
        result = await client.get("/api/1/vehicles")
        assert result == {"response": []}
        assert len(httpx_mock.get_requests()) == 2


class TestRateLimitExhaustsRetries:
    @pytest.mark.asyncio
    async def test_rate_limit_exhausts_retries(self, httpx_mock: HTTPXMock) -> None:
        client = TeslaFleetClient(access_token="tok123", region="na")
        # Return 429 for every attempt (initial + max retries)
        for _ in range(_RATE_LIMIT_MAX_RETRIES + 1):
            httpx_mock.add_response(
                url=f"{FLEET_BASE}/api/1/vehicles",
                status_code=429,
                headers={"retry-after": "0"},
            )
        with pytest.raises(RateLimitError):
            await client.get("/api/1/vehicles")
        assert len(httpx_mock.get_requests()) == _RATE_LIMIT_MAX_RETRIES + 1


class TestRateLimitCallbackInvoked:
    @pytest.mark.asyncio
    async def test_rate_limit_callback_invoked(self, httpx_mock: HTTPXMock) -> None:
        callback = AsyncMock()
        client = TeslaFleetClient(
            access_token="tok123",
            region="na",
            on_rate_limit_wait=callback,
        )
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            status_code=429,
            headers={"retry-after": "5"},
        )
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            json={"response": []},
        )
        result = await client.get("/api/1/vehicles")
        assert result == {"response": []}
        callback.assert_awaited_once_with(5, 1, _RATE_LIMIT_MAX_RETRIES)


class TestMissingScopesRaises:
    @pytest.mark.asyncio
    async def test_missing_scopes_raises(
        self, httpx_mock: HTTPXMock, client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/me",
            status_code=403,
            json={
                "response": None,
                "error": "Unauthorized missing scopes",
                "error_description": "",
            },
        )
        with pytest.raises(MissingScopesError) as exc_info:
            await client.get("/api/1/users/me")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_scopes_is_auth_error(
        self, httpx_mock: HTTPXMock, client: TeslaFleetClient
    ) -> None:
        """MissingScopesError should also be catchable as AuthError."""
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/me",
            status_code=403,
            json={"error": "Unauthorized missing scopes"},
        )
        with pytest.raises(AuthError):
            await client.get("/api/1/users/me")


class TestGeneric403RaisesAuthError:
    @pytest.mark.asyncio
    async def test_generic_403_raises_auth_error(
        self, httpx_mock: HTTPXMock, client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/123/command/door_lock",
            status_code=403,
            json={"error": "Forbidden"},
        )
        with pytest.raises(AuthError) as exc_info:
            await client.post("/api/1/vehicles/123/command/door_lock")
        assert exc_info.value.status_code == 403
        # Generic 403 should NOT be MissingScopesError
        assert not isinstance(exc_info.value, MissingScopesError)
