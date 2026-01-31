"""Tests for tescmd.api.energy — EnergyAPI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tescmd.api.energy import EnergyAPI
from tescmd.models.energy import CalendarHistory, LiveStatus, SiteInfo

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tescmd.api.client import TeslaFleetClient

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
SITE_ID = 67890


def _body(mock: HTTPXMock, idx: int = 0) -> dict[str, object]:
    """Parse the JSON body of the idx-th request."""
    return json.loads(mock.get_requests()[idx].content)  # type: ignore[no-any-return]


class TestListProducts:
    @pytest.mark.asyncio
    async def test_returns_list(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/products",
            json={
                "response": [
                    {
                        "energy_site_id": 67890,
                        "resource_type": "battery",
                        "site_name": "Home Powerwall",
                    },
                    {
                        "energy_site_id": 99999,
                        "resource_type": "solar",
                        "site_name": "Roof Solar",
                    },
                ]
            },
        )
        api = EnergyAPI(mock_client)
        result = await api.list_products()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["energy_site_id"] == 67890
        assert result[1]["resource_type"] == "solar"

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/products",
            json={"response": []},
        )
        api = EnergyAPI(mock_client)
        result = await api.list_products()

        assert result == []


class TestLiveStatus:
    @pytest.mark.asyncio
    async def test_returns_live_status(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/live_status",
            json={
                "response": {
                    "solar_power": 4500.0,
                    "battery_power": -1200.0,
                    "grid_power": 300.0,
                    "load_power": 3600.0,
                    "grid_status": "Active",
                    "battery_level": 85.0,
                    "percentage_charged": 85.0,
                }
            },
        )
        api = EnergyAPI(mock_client)
        result = await api.live_status(SITE_ID)

        assert isinstance(result, LiveStatus)
        assert result.solar_power == 4500.0
        assert result.battery_power == -1200.0
        assert result.grid_power == 300.0
        assert result.load_power == 3600.0
        assert result.grid_status == "Active"
        assert result.battery_level == 85.0

    @pytest.mark.asyncio
    async def test_handles_partial_fields(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/live_status",
            json={"response": {"solar_power": 1000.0}},
        )
        api = EnergyAPI(mock_client)
        result = await api.live_status(SITE_ID)

        assert isinstance(result, LiveStatus)
        assert result.solar_power == 1000.0
        assert result.battery_power is None
        assert result.grid_status is None


class TestSiteInfo:
    @pytest.mark.asyncio
    async def test_returns_site_info(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/site_info",
            json={
                "response": {
                    "energy_site_id": SITE_ID,
                    "site_name": "Home Powerwall",
                    "resource_type": "battery",
                    "backup_reserve_percent": 20.0,
                    "default_real_mode": "self_consumption",
                    "storm_mode_enabled": False,
                    "installation_date": "2023-06-15",
                }
            },
        )
        api = EnergyAPI(mock_client)
        result = await api.site_info(SITE_ID)

        assert isinstance(result, SiteInfo)
        assert result.energy_site_id == SITE_ID
        assert result.site_name == "Home Powerwall"
        assert result.resource_type == "battery"
        assert result.backup_reserve_percent == 20.0
        assert result.default_real_mode == "self_consumption"
        assert result.storm_mode_enabled is False
        assert result.installation_date == "2023-06-15"


class TestSetBackupReserve:
    @pytest.mark.asyncio
    async def test_sends_percent(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/backup",
            json={"response": {"result": "ok"}},
        )
        api = EnergyAPI(mock_client)
        result = await api.set_backup_reserve(SITE_ID, percent=50)

        assert isinstance(result, dict)
        assert result["result"] == "ok"
        body = _body(httpx_mock)
        assert body["backup_reserve_percent"] == 50

    @pytest.mark.asyncio
    async def test_sends_full_reserve(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {"result": "ok"}})
        api = EnergyAPI(mock_client)
        await api.set_backup_reserve(SITE_ID, percent=100)

        body = _body(httpx_mock)
        assert body["backup_reserve_percent"] == 100


class TestSetOperationMode:
    @pytest.mark.asyncio
    async def test_sends_mode(self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/operation",
            json={"response": {"result": "ok"}},
        )
        api = EnergyAPI(mock_client)
        result = await api.set_operation_mode(SITE_ID, mode="backup")

        assert isinstance(result, dict)
        body = _body(httpx_mock)
        assert body["default_real_mode"] == "backup"

    @pytest.mark.asyncio
    async def test_autonomous_mode(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {"result": "ok"}})
        api = EnergyAPI(mock_client)
        await api.set_operation_mode(SITE_ID, mode="autonomous")

        body = _body(httpx_mock)
        assert body["default_real_mode"] == "autonomous"


class TestSetStormMode:
    @pytest.mark.asyncio
    async def test_enable_storm_mode(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/storm_mode",
            json={"response": {"result": "ok"}},
        )
        api = EnergyAPI(mock_client)
        result = await api.set_storm_mode(SITE_ID, enabled=True)

        assert isinstance(result, dict)
        body = _body(httpx_mock)
        assert body["enabled"] is True

    @pytest.mark.asyncio
    async def test_disable_storm_mode(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {"result": "ok"}})
        api = EnergyAPI(mock_client)
        await api.set_storm_mode(SITE_ID, enabled=False)

        body = _body(httpx_mock)
        assert body["enabled"] is False


class TestTimeOfUseSettings:
    @pytest.mark.asyncio
    async def test_sends_tou_settings(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        tou_config = {
            "optimization_strategy": "economics",
            "periods": [
                {"start": 0, "end": 360, "rate": "off_peak"},
                {"start": 360, "end": 1440, "rate": "on_peak"},
            ],
        }
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/time_of_use_settings",
            json={"response": {"result": "ok"}},
        )
        api = EnergyAPI(mock_client)
        result = await api.time_of_use_settings(SITE_ID, settings=tou_config)

        assert isinstance(result, dict)
        body = _body(httpx_mock)
        assert body["tou_settings"] == tou_config


class TestChargingHistory:
    @pytest.mark.asyncio
    async def test_returns_calendar_history(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "serial_number": "PW-001",
                    "time_series": [
                        {"timestamp": "2024-01-01T00:00:00Z", "charging_energy": 5.2},
                        {"timestamp": "2024-01-02T00:00:00Z", "charging_energy": 3.8},
                    ],
                }
            },
        )
        api = EnergyAPI(mock_client)
        result = await api.charging_history(SITE_ID)

        assert isinstance(result, CalendarHistory)
        assert result.serial_number == "PW-001"
        assert len(result.time_series) == 2

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/energy_sites/{SITE_ID}/telemetry_history"
        assert request.url.params["kind"] == "charge"


class TestOffGridVehicleChargingReserve:
    @pytest.mark.asyncio
    async def test_sends_reserve(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/off_grid_vehicle_charging_reserve",
            json={"response": {"result": "ok"}},
        )
        api = EnergyAPI(mock_client)
        result = await api.off_grid_vehicle_charging_reserve(SITE_ID, reserve=80)

        assert isinstance(result, dict)
        body = _body(httpx_mock)
        assert body["off_grid_vehicle_charging_reserve_percent"] == 80


class TestGridImportExport:
    @pytest.mark.asyncio
    async def test_sends_config(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        config = {
            "disallow_charge_from_grid_with_solar_installed": True,
            "customer_preferred_export_rule": "pv_only",
        }
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/energy_sites/{SITE_ID}/grid_import_export",
            json={"response": {"result": "ok"}},
        )
        api = EnergyAPI(mock_client)
        result = await api.grid_import_export(SITE_ID, config=config)

        assert isinstance(result, dict)
        body = _body(httpx_mock)
        assert body["disallow_charge_from_grid_with_solar_installed"] is True
        assert body["customer_preferred_export_rule"] == "pv_only"


class TestTelemetryHistory:
    @pytest.mark.asyncio
    async def test_returns_calendar_history(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "serial_number": "SN123",
                    "time_series": [],
                }
            },
        )
        api = EnergyAPI(mock_client)
        result = await api.telemetry_history(12345)

        assert isinstance(result, CalendarHistory)
        assert result.serial_number == "SN123"
        assert result.time_series == []

        request = httpx_mock.get_requests()[0]
        assert "telemetry_history" in request.url.path
        assert request.url.params["kind"] == "charge"


class TestCalendarHistory:
    @pytest.mark.asyncio
    async def test_returns_calendar_history(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "serial_number": "PW-001",
                    "time_series": [
                        {
                            "timestamp": "2024-01-01T00:00:00Z",
                            "solar_energy_exported": 12.5,
                            "grid_energy_imported": 8.3,
                        },
                    ],
                }
            },
        )
        api = EnergyAPI(mock_client)
        result = await api.calendar_history(SITE_ID, kind="energy", period="day")

        assert isinstance(result, CalendarHistory)
        assert result.serial_number == "PW-001"
        assert len(result.time_series) == 1
        assert result.time_series[0]["solar_energy_exported"] == 12.5

        request = httpx_mock.get_requests()[0]
        assert request.url.path == f"/api/1/energy_sites/{SITE_ID}/calendar_history"
        assert request.url.params["kind"] == "energy"
        assert request.url.params["period"] == "day"

    @pytest.mark.asyncio
    async def test_passes_date_range(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"serial_number": "PW-001", "time_series": []}},
        )
        api = EnergyAPI(mock_client)
        await api.calendar_history(
            SITE_ID,
            kind="power",
            period="week",
            start_date="2024-01-01",
            end_date="2024-01-07",
        )

        request = httpx_mock.get_requests()[0]
        assert request.url.params["kind"] == "power"
        assert request.url.params["period"] == "week"
        assert request.url.params["start_date"] == "2024-01-01"
        assert request.url.params["end_date"] == "2024-01-07"

    @pytest.mark.asyncio
    async def test_omits_optional_date_params(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"serial_number": "PW-001", "time_series": []}},
        )
        api = EnergyAPI(mock_client)
        await api.calendar_history(SITE_ID, kind="energy", period="month")

        request = httpx_mock.get_requests()[0]
        assert "start_date" not in request.url.params
        assert "end_date" not in request.url.params

    @pytest.mark.asyncio
    async def test_passes_time_zone(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"serial_number": "PW-001", "time_series": []}},
        )
        api = EnergyAPI(mock_client)
        await api.calendar_history(SITE_ID, kind="energy", time_zone="America/Los_Angeles")

        request = httpx_mock.get_requests()[0]
        assert request.url.params["time_zone"] == "America/Los_Angeles"

    @pytest.mark.asyncio
    async def test_omits_time_zone_when_none(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"serial_number": "PW-001", "time_series": []}},
        )
        api = EnergyAPI(mock_client)
        await api.calendar_history(SITE_ID, kind="energy")

        request = httpx_mock.get_requests()[0]
        assert "time_zone" not in request.url.params
