"""Execution tests for the charge CLI commands.

Each test mocks the Fleet API via ``httpx_mock`` (pytest-httpx), invokes the
Click CLI through ``CliRunner``, and asserts on the JSON output envelope.
Read-commands (``charge status``) mock the ``vehicle_data`` GET endpoint.
Write-commands mock the corresponding POST ``/command/*`` endpoint.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"

# -- Reusable mock payloads ---------------------------------------------------

VEHICLE_DATA_RESPONSE: dict = {
    "response": {
        "vin": VIN,
        "display_name": "My Model 3",
        "state": "online",
        "vehicle_id": 123456,
        "charge_state": {
            "battery_level": 72,
            "battery_range": 220.5,
            "charging_state": "Complete",
            "charge_limit_soc": 80,
        },
    },
}

COMMAND_OK: dict = {"response": {"result": True, "reason": ""}}


# =============================================================================
# Read command — charge status
# =============================================================================


class TestChargeStatus:
    """Tests for ``tescmd charge status`` (read via vehicle_data GET)."""

    def test_charge_status_json(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """charge status returns charge_state fields in the JSON envelope."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=charge_state",
            method="GET",
            json=VEHICLE_DATA_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "status"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.status"
        assert parsed["data"]["battery_level"] == 72
        assert parsed["data"]["charging_state"] == "Complete"
        assert parsed["data"]["charge_limit_soc"] == 80

    def test_charge_status_battery_range(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """charge status includes battery_range in output."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=charge_state",
            method="GET",
            json=VEHICLE_DATA_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "status"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["data"]["battery_range"] == 220.5


# =============================================================================
# Simple write commands (no extra parameters)
# =============================================================================


class TestChargeStart:
    def test_charge_start(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_start",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "start"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.start"


class TestChargeStop:
    def test_charge_stop(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_stop",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "stop"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.stop"


class TestChargeLimitMax:
    def test_limit_max(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_max_range",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "limit-max"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.limit-max"


class TestChargeLimitStd:
    def test_limit_std(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_standard",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "limit-std"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.limit-std"


class TestChargePortOpen:
    def test_port_open(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_port_door_open",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "port-open"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.port-open"


class TestChargePortClose:
    def test_port_close(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_port_door_close",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "port-close"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.port-close"


# =============================================================================
# Parameterised write commands
# =============================================================================


class TestChargeLimit:
    def test_charge_limit_80(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_charge_limit",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "limit", VIN, "80"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.limit"

    def test_charge_limit_rejects_out_of_range(self) -> None:
        """charge limit rejects values outside 50-100."""
        runner = CliRunner()
        result = runner.invoke(cli, ["charge", "limit", "30"])
        assert result.exit_code != 0


class TestChargeAmps:
    def test_charge_amps_32(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_charging_amps",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "amps", VIN, "32"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.amps"

    def test_charge_amps_rejects_out_of_range(self) -> None:
        """charge amps rejects values outside 0-48."""
        runner = CliRunner()
        result = runner.invoke(cli, ["charge", "amps", "100"])
        assert result.exit_code != 0


class TestChargeSchedule:
    def test_schedule_enable(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_scheduled_charging",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "schedule", "--enable", "--time", "480"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.schedule"


# =============================================================================
# Scheduled departure
# =============================================================================


class TestChargeDeparture:
    def test_departure_enable(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_scheduled_departure",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "departure", "--time", "480", "--on"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.departure"


# =============================================================================
# Precondition schedule management
# =============================================================================


class TestPreconditionAdd:
    def test_precondition_add(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/add_precondition_schedule",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        schedule_json = json.dumps({"schedule": {"days_of_week": 127, "enabled": True}})
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "precondition-add", VIN, schedule_json],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.precondition-add"


class TestPreconditionRemove:
    def test_precondition_remove(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remove_precondition_schedule",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "precondition-remove", VIN, "1"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.precondition-remove"


# =============================================================================
# Managed charging
# =============================================================================


class TestManagedAmps:
    def test_managed_amps(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_managed_charge_current_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "managed-amps", VIN, "16"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "charge.managed-amps"
        assert parsed["data"]["response"]["result"] is True

    def test_managed_amps_sends_body(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_managed_charge_current_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "managed-amps", VIN, "24"],
            catch_exceptions=False,
        )
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["charging_amps"] == 24


# =============================================================================
# Output envelope structure
# =============================================================================


class TestOutputEnvelope:
    """Verify the JSON envelope structure shared by all write-commands."""

    def test_envelope_has_timestamp(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_start",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "start"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed

    def test_envelope_data_contains_result(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/charge_stop",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "charge", "stop"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert parsed["data"]["response"]["result"] is True
        assert parsed["data"]["response"]["reason"] == ""
