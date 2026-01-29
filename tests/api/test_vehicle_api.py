"""Tests for tescmd.api.vehicle — VehicleAPI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tescmd.api.vehicle import VehicleAPI
from tescmd.models.vehicle import Vehicle, VehicleData

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tescmd.api.client import TeslaFleetClient

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


class TestListVehicles:
    @pytest.mark.asyncio
    async def test_list_vehicles(
        self,
        httpx_mock: HTTPXMock,
        mock_client: TeslaFleetClient,
        sample_vehicle_list_response: dict[str, Any],
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles",
            json=sample_vehicle_list_response,
        )
        api = VehicleAPI(mock_client)
        vehicles = await api.list_vehicles()

        assert len(vehicles) == 1
        assert isinstance(vehicles[0], Vehicle)
        assert vehicles[0].vin == "5YJ3E1EA1NF000001"
        assert vehicles[0].display_name == "My Model 3"
        assert vehicles[0].state == "online"


class TestGetVehicleData:
    @pytest.mark.asyncio
    async def test_get_vehicle_data(
        self,
        httpx_mock: HTTPXMock,
        mock_client: TeslaFleetClient,
        sample_vehicle_data_response: dict[str, Any],
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/5YJ3E1EA1NF000001/vehicle_data",
            json=sample_vehicle_data_response,
        )
        api = VehicleAPI(mock_client)
        vdata = await api.get_vehicle_data("5YJ3E1EA1NF000001")

        assert isinstance(vdata, VehicleData)
        assert vdata.vin == "5YJ3E1EA1NF000001"
        assert vdata.charge_state is not None
        assert vdata.charge_state.battery_level == 72
        assert vdata.drive_state is not None
        assert vdata.drive_state.latitude == 37.7749


class TestGetVehicleDataWithEndpoints:
    @pytest.mark.asyncio
    async def test_get_vehicle_data_with_endpoints(
        self,
        httpx_mock: HTTPXMock,
        mock_client: TeslaFleetClient,
        sample_vehicle_data_response: dict[str, Any],
    ) -> None:
        httpx_mock.add_response(
            json=sample_vehicle_data_response,
        )
        api = VehicleAPI(mock_client)
        await api.get_vehicle_data(
            "5YJ3E1EA1NF000001",
            endpoints=["charge_state", "drive_state"],
        )

        request = httpx_mock.get_requests()[0]
        assert "endpoints=charge_state%3Bdrive_state" in str(request.url)


class TestWakeVehicle:
    @pytest.mark.asyncio
    async def test_wake_vehicle(
        self,
        httpx_mock: HTTPXMock,
        mock_client: TeslaFleetClient,
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/5YJ3E1EA1NF000001/wake_up",
            json={
                "response": {
                    "vin": "5YJ3E1EA1NF000001",
                    "display_name": "My Model 3",
                    "state": "online",
                    "vehicle_id": 123456,
                }
            },
        )
        api = VehicleAPI(mock_client)
        vehicle = await api.wake("5YJ3E1EA1NF000001")

        assert isinstance(vehicle, Vehicle)
        assert vehicle.vin == "5YJ3E1EA1NF000001"
        assert vehicle.state == "online"
