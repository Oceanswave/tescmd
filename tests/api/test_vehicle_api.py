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


VIN = "5YJ3E1EA1NF000001"


class TestGetVehicle:
    @pytest.mark.asyncio
    async def test_get_vehicle(self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}",
            json={
                "response": {
                    "vin": VIN,
                    "display_name": "My Model 3",
                    "state": "online",
                    "vehicle_id": 123456,
                }
            },
        )
        api = VehicleAPI(mock_client)
        vehicle = await api.get_vehicle(VIN)

        assert isinstance(vehicle, Vehicle)
        assert vehicle.vin == VIN


class TestNearbyChargingSites:
    @pytest.mark.asyncio
    async def test_nearby_charging_sites_returns_model(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        from tescmd.models.vehicle import NearbyChargingSites

        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/nearby_charging_sites",
            json={
                "response": {
                    "superchargers": [
                        {
                            "name": "SC 1",
                            "distance_miles": 2.5,
                            "total_stalls": 10,
                            "available_stalls": 5,
                        },
                    ],
                    "destination_charging": [
                        {"name": "Dest 1", "distance_miles": 1.0},
                    ],
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.nearby_charging_sites(VIN)

        assert isinstance(result, NearbyChargingSites)
        assert len(result.superchargers) == 1
        assert result.superchargers[0].name == "SC 1"
        assert len(result.destination_charging) == 1


class TestRecentAlerts:
    @pytest.mark.asyncio
    async def test_recent_alerts(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/recent_alerts",
            json={"response": [{"name": "ServiceRequired", "time": "2024-01-01"}]},
        )
        api = VehicleAPI(mock_client)
        alerts = await api.recent_alerts(VIN)

        assert len(alerts) == 1
        assert alerts[0]["name"] == "ServiceRequired"


class TestReleaseNotes:
    @pytest.mark.asyncio
    async def test_release_notes(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/release_notes",
            json={"response": {"release_notes": [{"title": "Update 2024.8"}]}},
        )
        api = VehicleAPI(mock_client)
        data = await api.release_notes(VIN)

        assert "release_notes" in data


class TestServiceData:
    @pytest.mark.asyncio
    async def test_service_data(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/service_data",
            json={"response": {"service_status": "in_service"}},
        )
        api = VehicleAPI(mock_client)
        data = await api.service_data(VIN)

        assert data["service_status"] == "in_service"


class TestListDrivers:
    @pytest.mark.asyncio
    async def test_list_drivers(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        from tescmd.models.sharing import ShareDriverInfo

        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/drivers",
            json={
                "response": [
                    {"share_user_id": 1, "email": "driver@test.com", "status": "active"},
                ]
            },
        )
        api = VehicleAPI(mock_client)
        drivers = await api.list_drivers(VIN)

        assert len(drivers) == 1
        assert isinstance(drivers[0], ShareDriverInfo)
        assert drivers[0].email == "driver@test.com"


# ------------------------------------------------------------------
# Extended vehicle data endpoint tests
# ------------------------------------------------------------------


class TestEligibleSubscriptions:
    @pytest.mark.asyncio
    async def test_eligible_subscriptions(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "eligible": True,
                    "subscriptions": [
                        {"name": "Premium Connectivity", "price": 9.99},
                    ],
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.eligible_subscriptions(VIN)

        assert result["eligible"] is True
        assert len(result["subscriptions"]) == 1
        assert result["subscriptions"][0]["name"] == "Premium Connectivity"

        request = httpx_mock.get_requests()[0]
        assert request.url.path == "/api/1/dx/vehicles/subscriptions/eligibility"
        assert f"vin={VIN}" in str(request.url)

    @pytest.mark.asyncio
    async def test_eligible_subscriptions_empty(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {}})
        api = VehicleAPI(mock_client)
        result = await api.eligible_subscriptions(VIN)

        assert result == {}


class TestEligibleUpgrades:
    @pytest.mark.asyncio
    async def test_eligible_upgrades(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "eligible": True,
                    "upgrades": [
                        {"name": "Full Self-Driving", "price": 12000},
                    ],
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.eligible_upgrades(VIN)

        assert result["eligible"] is True
        assert len(result["upgrades"]) == 1
        assert result["upgrades"][0]["name"] == "Full Self-Driving"

        request = httpx_mock.get_requests()[0]
        assert request.url.path == "/api/1/dx/vehicles/upgrades/eligibility"
        assert f"vin={VIN}" in str(request.url)

    @pytest.mark.asyncio
    async def test_eligible_upgrades_empty(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {}})
        api = VehicleAPI(mock_client)
        result = await api.eligible_upgrades(VIN)

        assert result == {}


class TestOptions:
    @pytest.mark.asyncio
    async def test_options(self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "codes": ["AD15", "AF00", "APH4", "AU3P"],
                    "descriptions": {
                        "AD15": "Model 3",
                        "AF00": "No Ludicrous Mode",
                    },
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.options(VIN)

        assert len(result["codes"]) == 4
        assert "AD15" in result["codes"]
        assert result["descriptions"]["AD15"] == "Model 3"

        request = httpx_mock.get_requests()[0]
        assert request.url.path == "/api/1/dx/vehicles/options"
        assert f"vin={VIN}" in str(request.url)

    @pytest.mark.asyncio
    async def test_options_empty(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {}})
        api = VehicleAPI(mock_client)
        result = await api.options(VIN)

        assert result == {}


class TestSpecs:
    @pytest.mark.asyncio
    async def test_specs(self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/specs",
            json={
                "response": {
                    "model": "Model 3",
                    "trim": "Long Range",
                    "range_miles": 358,
                    "acceleration_0_60_mph": 4.2,
                    "top_speed_mph": 145,
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.specs(VIN)

        assert result["model"] == "Model 3"
        assert result["trim"] == "Long Range"
        assert result["range_miles"] == 358

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/vehicles/{VIN}/specs"

    @pytest.mark.asyncio
    async def test_specs_empty(self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/specs",
            json={"response": {}},
        )
        api = VehicleAPI(mock_client)
        result = await api.specs(VIN)

        assert result == {}


class TestWarrantyDetails:
    @pytest.mark.asyncio
    async def test_warranty_details(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/dx/warranty/details",
            json={
                "response": {
                    "warranties": [
                        {
                            "type": "Basic Vehicle",
                            "expiration_date": "2028-06-15",
                            "expiration_miles": 50000,
                        },
                        {
                            "type": "Battery & Drive Unit",
                            "expiration_date": "2030-06-15",
                            "expiration_miles": 120000,
                        },
                    ],
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.warranty_details()

        assert len(result["warranties"]) == 2
        assert result["warranties"][0]["type"] == "Basic Vehicle"
        assert result["warranties"][1]["expiration_miles"] == 120000

        request = httpx_mock.get_requests()[0]
        assert request.url.path == "/api/1/dx/warranty/details"
        assert request.method == "GET"

    @pytest.mark.asyncio
    async def test_warranty_details_empty(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/dx/warranty/details",
            json={"response": {}},
        )
        api = VehicleAPI(mock_client)
        result = await api.warranty_details()

        assert result == {}


class TestFleetStatus:
    @pytest.mark.asyncio
    async def test_fleet_status(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/fleet_status",
            json={
                "response": {
                    "vehicles": [
                        {"vin": VIN, "state": "online"},
                    ],
                    "total": 1,
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.fleet_status()

        assert result["total"] == 1
        assert len(result["vehicles"]) == 1
        assert result["vehicles"][0]["vin"] == VIN
        assert result["vehicles"][0]["state"] == "online"

        request = httpx_mock.get_requests()[0]
        assert request.url.path == "/api/1/vehicles/fleet_status"
        assert request.method == "POST"

    @pytest.mark.asyncio
    async def test_fleet_status_empty(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/fleet_status",
            json={"response": {}},
        )
        api = VehicleAPI(mock_client)
        result = await api.fleet_status()

        assert result == {}


class TestFleetTelemetryConfig:
    @pytest.mark.asyncio
    async def test_fleet_telemetry_config(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/fleet_telemetry_config",
            json={
                "response": {
                    "hostname": "telemetry.example.com",
                    "port": 443,
                    "fields": {"BatteryLevel": {"interval_seconds": 60}},
                    "alert_types": ["service"],
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.fleet_telemetry_config(VIN)

        assert result["hostname"] == "telemetry.example.com"
        assert result["port"] == 443
        assert "BatteryLevel" in result["fields"]
        assert result["fields"]["BatteryLevel"]["interval_seconds"] == 60

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/vehicles/{VIN}/fleet_telemetry_config"
        assert request.method == "GET"

    @pytest.mark.asyncio
    async def test_fleet_telemetry_config_empty(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/fleet_telemetry_config",
            json={"response": {}},
        )
        api = VehicleAPI(mock_client)
        result = await api.fleet_telemetry_config(VIN)

        assert result == {}


class TestFleetTelemetryErrors:
    @pytest.mark.asyncio
    async def test_fleet_telemetry_errors(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/fleet_telemetry_errors",
            json={
                "response": {
                    "errors": [
                        {
                            "code": "CONN_TIMEOUT",
                            "message": "Connection timed out",
                            "timestamp": "2024-08-15T12:00:00Z",
                        },
                    ],
                    "total": 1,
                }
            },
        )
        api = VehicleAPI(mock_client)
        result = await api.fleet_telemetry_errors(VIN)

        assert result["total"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["code"] == "CONN_TIMEOUT"
        assert result["errors"][0]["message"] == "Connection timed out"

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/vehicles/{VIN}/fleet_telemetry_errors"
        assert request.method == "GET"

    @pytest.mark.asyncio
    async def test_fleet_telemetry_errors_empty(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/fleet_telemetry_errors",
            json={"response": {}},
        )
        api = VehicleAPI(mock_client)
        result = await api.fleet_telemetry_errors(VIN)

        assert result == {}
