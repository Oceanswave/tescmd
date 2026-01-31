"""Tests for tescmd.api.partner — PartnerAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tescmd.api.partner import PartnerAPI

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tescmd.api.client import TeslaFleetClient

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


class TestPublicKey:
    @pytest.mark.asyncio
    async def test_returns_dict(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/partner_accounts/public_key?domain=example.com",
            json={"response": {"public_key": "-----BEGIN PUBLIC KEY-----\nMFk..."}},
        )
        api = PartnerAPI(mock_client)
        result = await api.public_key(domain="example.com")

        assert isinstance(result, dict)
        assert "public_key" in result

    @pytest.mark.asyncio
    async def test_uses_get_with_domain_param(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"public_key": "pk"}},
        )
        api = PartnerAPI(mock_client)
        await api.public_key(domain="test.example.com")

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert "domain=test.example.com" in str(request.url)
        assert "/api/1/partner_accounts/public_key" in request.url.path


class TestFleetTelemetryErrorVins:
    @pytest.mark.asyncio
    async def test_returns_list_of_vins(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/partner_accounts/fleet_telemetry_error_vins",
            json={"response": ["VIN001", "VIN002"]},
        )
        api = PartnerAPI(mock_client)
        result = await api.fleet_telemetry_error_vins()

        assert isinstance(result, list)
        assert result == ["VIN001", "VIN002"]

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/partner_accounts/fleet_telemetry_error_vins",
            json={"response": []},
        )
        api = PartnerAPI(mock_client)
        result = await api.fleet_telemetry_error_vins()

        assert result == []

    @pytest.mark.asyncio
    async def test_uses_get_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": []})
        api = PartnerAPI(mock_client)
        await api.fleet_telemetry_error_vins()

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert request.url.path == "/api/1/partner_accounts/fleet_telemetry_error_vins"


class TestFleetTelemetryErrors:
    @pytest.mark.asyncio
    async def test_returns_list_of_errors(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/partner_accounts/fleet_telemetry_errors",
            json={
                "response": [
                    {
                        "vin": "VIN001",
                        "error": "connection_refused",
                        "timestamp": "2024-01-01T00:00:00Z",
                    },
                ]
            },
        )
        api = PartnerAPI(mock_client)
        result = await api.fleet_telemetry_errors()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["vin"] == "VIN001"
        assert result[0]["error"] == "connection_refused"

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/partner_accounts/fleet_telemetry_errors",
            json={"response": []},
        )
        api = PartnerAPI(mock_client)
        result = await api.fleet_telemetry_errors()

        assert result == []

    @pytest.mark.asyncio
    async def test_uses_get_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": []})
        api = PartnerAPI(mock_client)
        await api.fleet_telemetry_errors()

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert request.url.path == "/api/1/partner_accounts/fleet_telemetry_errors"
