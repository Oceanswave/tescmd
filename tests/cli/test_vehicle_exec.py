"""Tests for the vehicle CLI commands — full execution with mocked HTTP responses."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"


# ---------------------------------------------------------------------------
# vehicle list
# ---------------------------------------------------------------------------


class TestVehicleList:
    def test_list_vehicles(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles",
            json={
                "response": [
                    {
                        "vin": VIN,
                        "display_name": "Test",
                        "state": "online",
                        "vehicle_id": 123,
                    }
                ],
                "count": 1,
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--format", "json", "vehicle", "list"], catch_exceptions=False
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.list"
        assert isinstance(parsed["data"], list)
        assert len(parsed["data"]) == 1
        assert parsed["data"][0]["vin"] == VIN
        assert parsed["data"][0]["display_name"] == "Test"
        assert parsed["data"][0]["state"] == "online"

    def test_list_vehicles_empty(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles",
            json={"response": [], "count": 0},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--format", "json", "vehicle", "list"], catch_exceptions=False
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.list"
        assert parsed["data"] == []


# ---------------------------------------------------------------------------
# vehicle info
# ---------------------------------------------------------------------------


class TestVehicleInfo:
    def test_info_with_positional_vin(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data",
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "charge_state": {
                        "battery_level": 72,
                        "charging_state": "Complete",
                    },
                    "climate_state": {
                        "inside_temp": 22.0,
                        "is_climate_on": False,
                    },
                    "drive_state": {
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "heading": 180,
                    },
                    "vehicle_state": {
                        "locked": True,
                        "odometer": 15000.5,
                        "car_version": "2024.26.9",
                    },
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "info", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.info"
        assert parsed["data"]["vin"] == VIN
        assert parsed["data"]["charge_state"]["battery_level"] == 72
        assert parsed["data"]["vehicle_state"]["locked"] is True


# ---------------------------------------------------------------------------
# vehicle data
# ---------------------------------------------------------------------------


class TestVehicleData:
    def test_data_returns_full_payload(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data",
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "charge_state": {
                        "battery_level": 72,
                        "charging_state": "Complete",
                    },
                    "climate_state": {
                        "inside_temp": 22.0,
                        "is_climate_on": False,
                    },
                    "drive_state": {
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "heading": 180,
                    },
                    "vehicle_state": {
                        "locked": True,
                        "odometer": 15000.5,
                        "car_version": "2024.26.9",
                    },
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "data", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.data"
        assert parsed["data"]["vin"] == VIN
        assert parsed["data"]["climate_state"]["inside_temp"] == 22.0
        assert parsed["data"]["drive_state"]["latitude"] == 37.7749


# ---------------------------------------------------------------------------
# vehicle location
# ---------------------------------------------------------------------------


class TestVehicleLocation:
    def test_location_returns_drive_state(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "drive_state": {
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "heading": 180,
                    },
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "location", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.location"
        assert parsed["data"]["latitude"] == 37.7749
        assert parsed["data"]["longitude"] == -122.4194
        assert parsed["data"]["heading"] == 180

    def test_location_sends_drive_state_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "drive_state": {
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "heading": 180,
                    },
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "location", VIN],
            catch_exceptions=False,
        )
        request = httpx_mock.get_requests()[0]
        assert "endpoints=drive_state" in str(request.url)


# ---------------------------------------------------------------------------
# vehicle wake
# ---------------------------------------------------------------------------


class TestVehicleWake:
    def test_wake_returns_vehicle_state(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/wake_up",
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "vehicle_id": 123,
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "wake", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.wake"
        assert parsed["data"]["vin"] == VIN
        assert parsed["data"]["state"] == "online"


# ---------------------------------------------------------------------------
# vehicle alerts
# ---------------------------------------------------------------------------


class TestVehicleAlerts:
    def test_alerts_returns_list(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/recent_alerts",
            json={
                "response": [
                    {"name": "TestAlert", "time": "2024-01-01T00:00:00Z"},
                ]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "alerts", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.alerts"
        assert isinstance(parsed["data"], list)
        assert len(parsed["data"]) == 1
        assert parsed["data"][0]["name"] == "TestAlert"


# ---------------------------------------------------------------------------
# vehicle release-notes
# ---------------------------------------------------------------------------


class TestVehicleReleaseNotes:
    def test_release_notes_returns_data(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/release_notes",
            json={
                "response": {
                    "release_notes_html": "<p>Test release notes</p>",
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "release-notes", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.release-notes"
        assert parsed["data"]["release_notes_html"] == "<p>Test release notes</p>"


# ---------------------------------------------------------------------------
# vehicle service
# ---------------------------------------------------------------------------


class TestVehicleService:
    def test_service_returns_data(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/service_data",
            json={
                "response": {
                    "service_status": "active",
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "service", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.service"
        assert parsed["data"]["service_status"] == "active"


# ---------------------------------------------------------------------------
# vehicle drivers
# ---------------------------------------------------------------------------


class TestVehicleDrivers:
    def test_drivers_returns_list(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/drivers",
            json={
                "response": [
                    {"email": "test@example.com", "status": "active"},
                ]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "drivers", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.drivers"
        assert isinstance(parsed["data"], list)
        assert len(parsed["data"]) == 1
        assert parsed["data"][0]["email"] == "test@example.com"
        assert parsed["data"][0]["status"] == "active"


# ---------------------------------------------------------------------------
# vehicle rename
# ---------------------------------------------------------------------------


class TestVehicleRename:
    def test_rename_sends_command(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        # auto_wake tries the operation first; if it succeeds the wake
        # endpoint is never called, so we only mock the command itself.
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_vehicle_name",
            json={
                "response": {
                    "result": True,
                    "reason": "",
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "rename", VIN, "New Name"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.rename"
        assert parsed["data"]["response"]["result"] is True

    def test_rename_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_vehicle_name",
            json={
                "response": {
                    "result": True,
                    "reason": "",
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "rename", VIN, "My Tesla"],
            catch_exceptions=False,
        )
        # Find the POST to set_vehicle_name and verify the JSON body
        requests = httpx_mock.get_requests()
        cmd_request = [
            r for r in requests if "set_vehicle_name" in str(r.url)
        ]
        assert len(cmd_request) == 1
        body = json.loads(cmd_request[0].content)
        assert body["vehicle_name"] == "My Tesla"


# ---------------------------------------------------------------------------
# vehicle mobile-access
# ---------------------------------------------------------------------------


class TestVehicleMobileAccess:
    def test_mobile_access_enabled(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/mobile_enabled",
            json={"response": True},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "mobile-access", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.mobile-access"
        assert parsed["data"]["mobile_enabled"] is True

    def test_mobile_access_disabled(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/mobile_enabled",
            json={"response": False},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "mobile-access", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["data"]["mobile_enabled"] is False


# ---------------------------------------------------------------------------
# vehicle nearby-chargers
# ---------------------------------------------------------------------------


class TestVehicleNearbyChargers:
    def test_nearby_chargers_returns_data(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/nearby_charging_sites",
            json={
                "response": {
                    "superchargers": [
                        {
                            "name": "Test SC",
                            "distance_miles": 2.5,
                            "total_stalls": 10,
                            "available_stalls": 5,
                        }
                    ],
                    "destination_charging": [
                        {"name": "Test Dest", "distance_miles": 1.0}
                    ],
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "nearby-chargers", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.nearby-chargers"
        assert len(parsed["data"]["superchargers"]) == 1
        assert parsed["data"]["superchargers"][0]["name"] == "Test SC"
        assert len(parsed["data"]["destination_charging"]) == 1
        assert parsed["data"]["destination_charging"][0]["name"] == "Test Dest"

    def test_nearby_chargers_empty(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/nearby_charging_sites",
            json={
                "response": {
                    "superchargers": [],
                    "destination_charging": [],
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "nearby-chargers", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["data"]["superchargers"] == []
        assert parsed["data"]["destination_charging"] == []
