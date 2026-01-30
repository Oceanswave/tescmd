"""Execution tests for the raw CLI commands.

Each test mocks the Fleet API via ``httpx_mock`` (pytest-httpx), invokes the
Click CLI through ``CliRunner``, and asserts on the JSON output envelope.

``raw get`` sends a GET to an arbitrary path.
``raw post`` sends a POST to an arbitrary path.
Both bypass VehicleAPI/CommandAPI and use ``get_client()`` directly.
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

COMMAND_OK: dict = {"response": {"result": True, "reason": ""}}


# =============================================================================
# raw get
# =============================================================================


class TestRawGet:
    """Tests for ``tescmd raw get PATH``."""

    def test_raw_get(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """raw get wraps the entire API response in data."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles",
            json={"response": [{"vin": VIN}], "count": 1},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "raw", "get", "/api/1/vehicles"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "raw.get"
        assert parsed["data"]["response"] == [{"vin": VIN}]
        assert parsed["data"]["count"] == 1

    def test_raw_get_with_params(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """raw get --params passes query parameters to the request."""
        httpx_mock.add_response(
            json={"response": {"vin": VIN, "state": "online"}},
        )
        runner = CliRunner()
        params_json = json.dumps({"endpoints": "charge_state"})
        result = runner.invoke(
            cli,
            [
                "--format",
                "json",
                "raw",
                "get",
                f"/api/1/vehicles/{VIN}/vehicle_data",
                "--params",
                params_json,
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "raw.get"

    def test_raw_get_has_timestamp(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """raw get includes a timestamp in the JSON envelope."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles",
            json={"response": [], "count": 0},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "raw", "get", "/api/1/vehicles"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "timestamp" in parsed

    def test_raw_get_empty_response(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """raw get handles empty list responses."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles",
            json={"response": [], "count": 0},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "raw", "get", "/api/1/vehicles"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["data"]["response"] == []
        assert parsed["data"]["count"] == 0


# =============================================================================
# raw post
# =============================================================================


class TestRawPost:
    """Tests for ``tescmd raw post PATH``."""

    def test_raw_post(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """raw post sends POST and wraps the response in data."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/flash_lights",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--format",
                "json",
                "raw",
                "post",
                f"/api/1/vehicles/{VIN}/command/flash_lights",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "raw.post"
        assert parsed["data"]["response"]["result"] is True
        assert parsed["data"]["response"]["reason"] == ""

    def test_raw_post_with_body(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """raw post --body sends JSON body in the request."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_charge_limit",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        body_json = json.dumps({"percent": 80})
        result = runner.invoke(
            cli,
            [
                "--format",
                "json",
                "raw",
                "post",
                f"/api/1/vehicles/{VIN}/command/set_charge_limit",
                "--body",
                body_json,
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "raw.post"

    def test_raw_post_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """raw post --body forwards the JSON body to the Fleet API."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_charge_limit",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        body_json = json.dumps({"percent": 90})
        runner.invoke(
            cli,
            [
                "--format",
                "json",
                "raw",
                "post",
                f"/api/1/vehicles/{VIN}/command/set_charge_limit",
                "--body",
                body_json,
            ],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        sent_body = json.loads(requests[0].content)
        assert sent_body["percent"] == 90

    def test_raw_post_has_timestamp(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """raw post includes a timestamp in the JSON envelope."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/flash_lights",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--format",
                "json",
                "raw",
                "post",
                f"/api/1/vehicles/{VIN}/command/flash_lights",
            ],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed
