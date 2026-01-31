"""Tests for the climate CLI commands — execution via httpx_mock.

Each test class covers a single climate subcommand. Read-commands (``status``)
mock GET vehicle_data; write-commands mock POST to the corresponding command
endpoint. All write-command tests use ``--format json --wake`` so that
``auto_wake`` proceeds without an interactive prompt.
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

CMD_OK: dict[str, object] = {"response": {"result": True, "reason": ""}}

VEHICLE_DATA_CLIMATE: dict[str, object] = {
    "response": {
        "vin": VIN,
        "state": "online",
        "climate_state": {
            "inside_temp": 22.0,
            "outside_temp": 18.0,
            "driver_temp_setting": 21.0,
            "passenger_temp_setting": 21.0,
            "is_climate_on": False,
        },
    }
}


def _request_body(httpx_mock: HTTPXMock, idx: int = 0) -> dict[str, object]:
    """Return the parsed JSON body of the *idx*-th captured request."""
    return json.loads(httpx_mock.get_requests()[idx].content)  # type: ignore[no-any-return]


def _request_url(httpx_mock: HTTPXMock, idx: int = 0) -> str:
    """Return the URL path of the *idx*-th captured request."""
    return str(httpx_mock.get_requests()[idx].url)


# ---------------------------------------------------------------------------
# climate status (read command — GET vehicle_data)
# ---------------------------------------------------------------------------


class TestClimateStatus:
    def test_status_returns_climate_state(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=climate_state",
            json=VEHICLE_DATA_CLIMATE,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "climate", "status"])
        assert result.exit_code == 0, result.output

        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["command"] == "climate.status"
        assert data["data"]["inside_temp"] == 22.0
        assert data["data"]["is_climate_on"] is False


# ---------------------------------------------------------------------------
# climate on
# ---------------------------------------------------------------------------


class TestClimateOn:
    def test_climate_on_posts_correct_endpoint(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/auto_conditioning_start",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "climate", "on"])
        assert result.exit_code == 0, result.output

        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# climate off
# ---------------------------------------------------------------------------


class TestClimateOff:
    def test_climate_off_posts_correct_endpoint(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/auto_conditioning_stop",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "climate", "off"])
        assert result.exit_code == 0, result.output

        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# climate set (Fahrenheit, the default)
# ---------------------------------------------------------------------------


class TestClimateSetFahrenheit:
    def test_set_72f_converts_to_celsius(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_temps",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli, ["--format", "json", "--wake", "climate", "set", VIN, "72"]
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        # 72F = (72 - 32) * 5/9 = 22.222...
        assert abs(float(body["driver_temp"]) - 22.22) < 0.01
        assert abs(float(body["passenger_temp"]) - 22.22) < 0.01


# ---------------------------------------------------------------------------
# climate set --celsius
# ---------------------------------------------------------------------------


class TestClimateSetCelsius:
    def test_set_22c_sent_directly(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_temps",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "set", VIN, "22", "--celsius"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert float(body["driver_temp"]) == 22.0
        assert float(body["passenger_temp"]) == 22.0


# ---------------------------------------------------------------------------
# climate precondition --on
# ---------------------------------------------------------------------------


class TestClimatePrecondition:
    def test_precondition_on(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_preconditioning_max",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "precondition", "--on"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["on"] is True


# ---------------------------------------------------------------------------
# climate seat
# ---------------------------------------------------------------------------


class TestClimateSeat:
    def test_seat_driver_level_3(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_seat_heater_request",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "seat", VIN, "driver", "3"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["seat_position"] == 0  # driver -> seat index 0
        assert body["level"] == 3

    def test_seat_rear_left_level_2(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_seat_heater_request",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "seat", VIN, "rear-left", "2"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["seat_position"] == 2  # rear-left -> seat index 2
        assert body["level"] == 2


# ---------------------------------------------------------------------------
# climate seat-cool
# ---------------------------------------------------------------------------


class TestClimateSeatCool:
    def test_seat_cool_driver_level_2(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_seat_cooler_request",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "seat-cool", VIN, "driver", "2"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["seat_position"] == 0  # driver -> seat index 0
        assert body["seat_cooler_level"] == 2


# ---------------------------------------------------------------------------
# climate wheel-heater
# ---------------------------------------------------------------------------


class TestClimateWheelHeater:
    def test_wheel_heater_on(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_steering_wheel_heater_request",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "wheel-heater", "--on"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["on"] is True


# ---------------------------------------------------------------------------
# climate overheat
# ---------------------------------------------------------------------------


class TestClimateOverheat:
    def test_overheat_on(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_cabin_overheat_protection",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "overheat", "--on"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["on"] is True
        assert body["fan_only"] is False

    def test_overheat_on_fan_only(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_cabin_overheat_protection",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            [
                "--format",
                "json",
                "--wake",
                "climate",
                "overheat",
                "--on",
                "--fan-only",
            ],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["on"] is True
        assert body["fan_only"] is True


# ---------------------------------------------------------------------------
# climate bioweapon
# ---------------------------------------------------------------------------


class TestClimateBioweapon:
    def test_bioweapon_on(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_bioweapon_mode",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "bioweapon", "--on"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["on"] is True
        assert body["manual_override"] is False


# ---------------------------------------------------------------------------
# climate cop-temp
# ---------------------------------------------------------------------------


class TestClimateCopTemp:
    def test_cop_temp_level_2(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_cop_temp",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "cop-temp", VIN, "2"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["cop_temp"] == 2


# ---------------------------------------------------------------------------
# climate auto-seat
# ---------------------------------------------------------------------------


class TestClimateAutoSeat:
    def test_auto_seat_driver_on(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_auto_seat_climate_request",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "auto-seat", VIN, "driver", "--on"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["auto_seat_position"] == 0  # driver -> seat index 0
        assert body["auto_climate_on"] is True


# ---------------------------------------------------------------------------
# climate auto-wheel
# ---------------------------------------------------------------------------


class TestClimateAutoWheel:
    def test_auto_wheel_on(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_auto_steering_wheel_heat_climate_request",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "auto-wheel", "--on"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["on"] is True


# ---------------------------------------------------------------------------
# climate wheel-level
# ---------------------------------------------------------------------------


class TestClimateWheelLevel:
    def test_wheel_level_3(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_steering_wheel_heat_level_request",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "wheel-level", VIN, "3"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["level"] == 3


# ---------------------------------------------------------------------------
# climate keeper
# ---------------------------------------------------------------------------


class TestClimateKeeper:
    def test_keeper_dog(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_climate_keeper_mode",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "keeper", VIN, "dog"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["climate_keeper_mode"] == 2  # dog -> 2

    def test_keeper_camp(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_climate_keeper_mode",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "keeper", VIN, "camp"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["climate_keeper_mode"] == 3  # camp -> 3

    def test_keeper_off(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_climate_keeper_mode",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "climate", "keeper", VIN, "off"],
        )
        assert result.exit_code == 0, result.output

        body = _request_body(httpx_mock)
        assert body["climate_keeper_mode"] == 0  # off -> 0
