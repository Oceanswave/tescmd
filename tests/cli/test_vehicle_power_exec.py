"""Execution tests for vehicle power management CLI commands (low-power, accessory-power)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"
CMD_OK: dict = {"response": {"result": True, "reason": ""}}


def _cmd_request(httpx_mock: HTTPXMock, fragment: str) -> dict[str, object]:
    """Return the JSON body of the request whose URL contains *fragment*."""
    requests = httpx_mock.get_requests()
    matches = [r for r in requests if fragment in str(r.url)]
    assert len(matches) == 1, f"Expected 1 request matching '{fragment}', got {len(matches)}"
    content = matches[0].content
    if content:
        return json.loads(content)  # type: ignore[no-any-return]
    return {}


# ---------------------------------------------------------------------------
# vehicle low-power
# ---------------------------------------------------------------------------


class TestVehicleLowPower:
    def test_low_power_on(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_low_power_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "low-power", "--on", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.low-power"
        body = _cmd_request(httpx_mock, "set_low_power_mode")
        assert body["enable"] is True

    def test_low_power_off(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_low_power_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "low-power", "--off", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "set_low_power_mode")
        assert body["enable"] is False


# ---------------------------------------------------------------------------
# vehicle accessory-power
# ---------------------------------------------------------------------------


class TestVehicleAccessoryPower:
    def test_accessory_power_on(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/keep_accessory_power_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "accessory-power", "--on", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.accessory-power"
        body = _cmd_request(httpx_mock, "keep_accessory_power_mode")
        assert body["enable"] is True

    def test_accessory_power_off(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/keep_accessory_power_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "vehicle", "accessory-power", "--off", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "keep_accessory_power_mode")
        assert body["enable"] is False
