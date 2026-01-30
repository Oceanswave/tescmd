"""Execution tests for the software CLI commands.

Each test mocks the Fleet API via ``httpx_mock`` (pytest-httpx), invokes the
Click CLI through ``CliRunner``, and asserts on the JSON output envelope.

``software status`` reads ``vehicle_data`` with endpoints=vehicle_state.
``software schedule`` and ``software cancel`` use ``execute_command()`` and
POST to ``/api/1/vehicles/{vin}/command/{method}``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"

COMMAND_OK: dict[str, Any] = {"response": {"result": True, "reason": ""}}

VEHICLE_DATA_WITH_SOFTWARE: dict[str, Any] = {
    "response": {
        "vin": VIN,
        "state": "online",
        "vehicle_state": {
            "car_version": "2024.26.9",
            "software_update": {
                "status": "",
                "version": "",
            },
        },
    },
}


def _request_body(httpx_mock: HTTPXMock, idx: int = 0) -> dict[str, Any]:
    """Parse the JSON body of the idx-th captured request."""
    return json.loads(httpx_mock.get_requests()[idx].content)  # type: ignore[no-any-return]


# =============================================================================
# software status (read command — vehicle_data GET)
# =============================================================================


class TestSoftwareStatus:
    """Tests for ``tescmd software status``."""

    def test_software_status(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """software status returns car_version and software_update."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=vehicle_state",
            method="GET",
            json=VEHICLE_DATA_WITH_SOFTWARE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "status"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "software.status"
        assert parsed["data"]["car_version"] == "2024.26.9"
        assert "software_update" in parsed["data"]
        assert parsed["data"]["software_update"]["status"] == ""

    def test_software_status_with_pending_update(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software status shows pending update details."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=vehicle_state",
            method="GET",
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "vehicle_state": {
                        "car_version": "2024.26.9",
                        "software_update": {
                            "status": "available",
                            "version": "2024.32.1",
                        },
                    },
                },
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "status"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "software.status"
        assert parsed["data"]["car_version"] == "2024.26.9"
        assert "software_update" in parsed["data"]
        assert parsed["data"]["software_update"]["status"] == "available"
        assert parsed["data"]["software_update"]["version"] == "2024.32.1"

    def test_software_status_sends_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software status requests vehicle_state endpoint specifically."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=vehicle_state",
            method="GET",
            json=VEHICLE_DATA_WITH_SOFTWARE,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "status"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "endpoints=vehicle_state" in str(requests[0].url)

    def test_software_status_has_timestamp(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software status includes a timestamp in the JSON envelope."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=vehicle_state",
            method="GET",
            json=VEHICLE_DATA_WITH_SOFTWARE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "status"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed


# =============================================================================
# software schedule (write command)
# =============================================================================


class TestSoftwareSchedule:
    """Tests for ``tescmd software schedule VIN SECONDS``."""

    def test_software_schedule(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """software schedule posts to /command/schedule_software_update."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/schedule_software_update",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "schedule", VIN, "120"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "software.schedule"
        assert parsed["data"]["response"]["result"] is True

    def test_software_schedule_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software schedule sends offset_sec in the request body."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/schedule_software_update",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "schedule", VIN, "300"],
            catch_exceptions=False,
        )
        body = _request_body(httpx_mock)
        assert body["offset_sec"] == 300

    def test_software_schedule_zero_seconds(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software schedule accepts 0 seconds (install now)."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/schedule_software_update",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "schedule", VIN, "0"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "software.schedule"


# =============================================================================
# software cancel (write command)
# =============================================================================


class TestSoftwareCancel:
    """Tests for ``tescmd software cancel``."""

    def test_software_cancel(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """software cancel posts to /command/cancel_software_update."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/cancel_software_update",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "cancel"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "software.cancel"
        assert parsed["data"]["response"]["result"] is True

    def test_software_cancel_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software cancel sends POST to cancel_software_update endpoint."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/cancel_software_update",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "cancel"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "cancel_software_update" in str(requests[0].url)
        assert requests[0].method == "POST"

    def test_software_cancel_has_timestamp(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software cancel includes a timestamp in the JSON envelope."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/cancel_software_update",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "cancel"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed


# =============================================================================
# Output envelope structure
# =============================================================================


class TestSoftwareOutputEnvelope:
    """Verify the JSON envelope structure for software commands."""

    def test_status_envelope_data_keys(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """software status data has car_version and software_update."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=vehicle_state",
            method="GET",
            json=VEHICLE_DATA_WITH_SOFTWARE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "status"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "car_version" in parsed["data"]
        assert "software_update" in parsed["data"]

    def test_command_envelope_data_has_result(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """Write-command data contains response.result and response.reason."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/cancel_software_update",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "software", "cancel"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert parsed["data"]["response"]["result"] is True
        assert parsed["data"]["response"]["reason"] == ""
