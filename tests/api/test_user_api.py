"""Tests for tescmd.api.user — UserAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tescmd.api.user import UserAPI
from tescmd.models.user import FeatureConfig, UserInfo, UserRegion, VehicleOrder

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tescmd.api.client import TeslaFleetClient

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


class TestMe:
    @pytest.mark.asyncio
    async def test_returns_user_info(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/me",
            json={
                "response": {
                    "email": "owner@example.com",
                    "full_name": "Test Owner",
                    "profile_image_url": "https://img.example.com/avatar.jpg",
                }
            },
        )
        api = UserAPI(mock_client)
        result = await api.me()

        assert isinstance(result, UserInfo)
        assert result.email == "owner@example.com"
        assert result.full_name == "Test Owner"
        assert result.profile_image_url == "https://img.example.com/avatar.jpg"

    @pytest.mark.asyncio
    async def test_handles_partial_fields(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/me",
            json={"response": {"email": "user@test.com"}},
        )
        api = UserAPI(mock_client)
        result = await api.me()

        assert isinstance(result, UserInfo)
        assert result.email == "user@test.com"
        assert result.full_name is None
        assert result.profile_image_url is None

    @pytest.mark.asyncio
    async def test_uses_get_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {"email": "u@t.com"}})
        api = UserAPI(mock_client)
        await api.me()

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert request.url.path == "/api/1/users/me"


class TestRegion:
    @pytest.mark.asyncio
    async def test_returns_user_region(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/region",
            json={
                "response": {
                    "region": "na",
                    "fleet_api_base_url": "https://fleet-api.prd.na.vn.cloud.tesla.com",
                }
            },
        )
        api = UserAPI(mock_client)
        result = await api.region()

        assert isinstance(result, UserRegion)
        assert result.region == "na"
        assert result.fleet_api_base_url == "https://fleet-api.prd.na.vn.cloud.tesla.com"

    @pytest.mark.asyncio
    async def test_eu_region(self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/region",
            json={
                "response": {
                    "region": "eu",
                    "fleet_api_base_url": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
                }
            },
        )
        api = UserAPI(mock_client)
        result = await api.region()

        assert isinstance(result, UserRegion)
        assert result.region == "eu"
        assert result.fleet_api_base_url == "https://fleet-api.prd.eu.vn.cloud.tesla.com"

    @pytest.mark.asyncio
    async def test_uses_get_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {"region": "na"}})
        api = UserAPI(mock_client)
        await api.region()

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert request.url.path == "/api/1/users/region"


class TestOrders:
    @pytest.mark.asyncio
    async def test_returns_list_of_vehicle_orders(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/orders",
            json={
                "response": [
                    {
                        "order_id": "ORD-001",
                        "vin": "5YJ3E1EA1NF000001",
                        "model": "Model 3",
                        "status": "delivered",
                    },
                    {
                        "order_id": "ORD-002",
                        "vin": "7SAYGDEE5PA000002",
                        "model": "Model Y",
                        "status": "in_transit",
                    },
                ]
            },
        )
        api = UserAPI(mock_client)
        result = await api.orders()

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(o, VehicleOrder) for o in result)
        assert result[0].order_id == "ORD-001"
        assert result[0].vin == "5YJ3E1EA1NF000001"
        assert result[0].model == "Model 3"
        assert result[0].status == "delivered"
        assert result[1].order_id == "ORD-002"
        assert result[1].model == "Model Y"
        assert result[1].status == "in_transit"

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/orders",
            json={"response": []},
        )
        api = UserAPI(mock_client)
        result = await api.orders()

        assert result == []

    @pytest.mark.asyncio
    async def test_handles_partial_fields(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": [{"order_id": "ORD-099"}]},
        )
        api = UserAPI(mock_client)
        result = await api.orders()

        assert len(result) == 1
        assert result[0].order_id == "ORD-099"
        assert result[0].vin is None
        assert result[0].model is None
        assert result[0].status is None

    @pytest.mark.asyncio
    async def test_uses_get_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": []})
        api = UserAPI(mock_client)
        await api.orders()

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert request.url.path == "/api/1/users/orders"


class TestFeatureConfig:
    @pytest.mark.asyncio
    async def test_returns_feature_config(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/feature_config",
            json={
                "response": {
                    "signaling": {
                        "enabled": True,
                        "ble_supported": False,
                    },
                }
            },
        )
        api = UserAPI(mock_client)
        result = await api.feature_config()

        assert isinstance(result, FeatureConfig)
        assert result.signaling is not None
        assert result.signaling["enabled"] is True
        assert result.signaling["ble_supported"] is False

    @pytest.mark.asyncio
    async def test_handles_null_signaling(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/users/feature_config",
            json={"response": {}},
        )
        api = UserAPI(mock_client)
        result = await api.feature_config()

        assert isinstance(result, FeatureConfig)
        assert result.signaling is None

    @pytest.mark.asyncio
    async def test_uses_get_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {}})
        api = UserAPI(mock_client)
        await api.feature_config()

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert request.url.path == "/api/1/users/feature_config"
