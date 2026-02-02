"""Tests for trunk CLI commands — end-to-end execution with mocked HTTP."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"
CMD_OK: dict[str, Any] = {"response": {"result": True, "reason": ""}}

VEHICLE_DATA_WITH_DRIVE_STATE: dict[str, Any] = {
    "response": {
        "vin": VIN,
        "state": "online",
        "drive_state": {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "heading": 180,
        },
    },
}


def _request_body(httpx_mock: HTTPXMock, idx: int = 0) -> dict[str, Any]:
    """Parse the JSON body of the idx-th captured request."""
    return json.loads(httpx_mock.get_requests()[idx].content)  # type: ignore[no-any-return]


def _request_url(httpx_mock: HTTPXMock, idx: int = 0) -> str:
    """Return the full URL string of the idx-th captured request."""
    return str(httpx_mock.get_requests()[idx].url)


# ---------------------------------------------------------------------------
# trunk open
# ---------------------------------------------------------------------------


class TestTrunkOpen:
    def test_open_sends_actuate_trunk_rear(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/actuate_trunk",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "open"])

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["which_trunk"] == "rear"

    def test_open_returns_success_json(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(json=CMD_OK)
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "open"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# trunk close
# ---------------------------------------------------------------------------


class TestTrunkClose:
    def test_close_sends_actuate_trunk_rear(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/actuate_trunk",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "close"])

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["which_trunk"] == "rear"

    def test_close_hits_correct_endpoint(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(json=CMD_OK)
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "close"])

        assert result.exit_code == 0
        req_url = _request_url(httpx_mock)
        assert f"/api/1/vehicles/{VIN}/command/actuate_trunk" in req_url


# ---------------------------------------------------------------------------
# trunk frunk
# ---------------------------------------------------------------------------


class TestTrunkFrunk:
    def test_frunk_sends_actuate_trunk_front(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/actuate_trunk",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "frunk"])

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["which_trunk"] == "front"

    def test_frunk_returns_success_json(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(json=CMD_OK)
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "frunk"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# trunk sunroof
# ---------------------------------------------------------------------------


class TestTrunkSunroof:
    def test_sunroof_vent(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/sun_roof_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli, ["--format", "json", "--wake", "trunk", "sunroof", "--state", "vent"]
        )

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["state"] == "vent"

    def test_sunroof_close(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/sun_roof_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli, ["--format", "json", "--wake", "trunk", "sunroof", "--state", "close"]
        )

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["state"] == "close"

    def test_sunroof_stop(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        """--state stop sends state=stop to the API."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/sun_roof_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli, ["--format", "json", "--wake", "trunk", "sunroof", "--state", "stop"]
        )

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["state"] == "stop"

    def test_sunroof_requires_state(self, cli_env: dict[str, str]) -> None:
        """sunroof now requires --state option."""
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "sunroof"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# trunk window
# ---------------------------------------------------------------------------


class TestTrunkWindowVent:
    def test_window_vent_default_coords(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        """--vent without --lat/--lon uses 0.0/0.0."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/window_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli, ["--format", "json", "--wake", "trunk", "window", "--vent"]
        )

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["command"] == "vent"
        assert body["lat"] == 0.0
        assert body["lon"] == 0.0

    def test_window_vent_with_explicit_coords(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        """--vent with --lat/--lon passes those coords through."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/window_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            [
                "--format",
                "json",
                "--wake",
                "trunk",
                "window",
                "--vent",
                "--lat",
                "40.71",
                "--lon",
                "-74.01",
            ],
        )

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["command"] == "vent"
        assert body["lat"] == pytest.approx(40.71)
        assert body["lon"] == pytest.approx(-74.01)

    def test_window_default_is_vent(self, httpx_mock: HTTPXMock, cli_env: dict[str, str]) -> None:
        """When neither --vent nor --close is given, default is vent."""
        httpx_mock.add_response(json=CMD_OK)
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "window"])

        assert result.exit_code == 0
        body = _request_body(httpx_mock)
        assert body["command"] == "vent"


class TestTrunkWindowClose:
    def test_window_close_with_explicit_coords(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        """--close with --lat/--lon sends those coords directly."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/window_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            [
                "--format",
                "json",
                "--wake",
                "trunk",
                "window",
                "--close",
                "--lat",
                "37.77",
                "--lon",
                "-122.42",
            ],
        )

        assert result.exit_code == 0, result.output
        body = _request_body(httpx_mock)
        assert body["command"] == "close"
        assert body["lat"] == pytest.approx(37.77)
        assert body["lon"] == pytest.approx(-122.42)

    def test_window_close_fetches_location_when_no_coords(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        """--close without --lat/--lon fetches vehicle_data for drive_state coords."""
        # First request: vehicle_data to get drive_state location
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=drive_state%3Blocation_data",
            json=VEHICLE_DATA_WITH_DRIVE_STATE,
        )
        # Second request: window_control command
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/window_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            ["--format", "json", "--wake", "trunk", "window", "--close"],
        )

        assert result.exit_code == 0, result.output

        # Verify two requests were made
        requests = httpx_mock.get_requests()
        assert len(requests) == 2

        # First request should be the vehicle_data GET
        assert requests[0].method == "GET"
        assert "vehicle_data" in str(requests[0].url)
        assert "drive_state" in str(requests[0].url)

        # Second request should be the window_control POST
        assert requests[1].method == "POST"
        assert "window_control" in str(requests[1].url)
        body = json.loads(requests[1].content)
        assert body["command"] == "close"
        assert body["lat"] == pytest.approx(37.7749)
        assert body["lon"] == pytest.approx(-122.4194)

    def test_window_close_hits_correct_endpoint(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/window_control",
            json=CMD_OK,
        )
        result = CliRunner().invoke(
            cli,
            [
                "--format",
                "json",
                "--wake",
                "trunk",
                "window",
                "--close",
                "--lat",
                "37.77",
                "--lon",
                "-122.42",
            ],
        )

        assert result.exit_code == 0
        req_url = _request_url(httpx_mock)
        assert f"/api/1/vehicles/{VIN}/command/window_control" in req_url


# ---------------------------------------------------------------------------
# trunk tonneau-open / tonneau-close / tonneau-stop
# ---------------------------------------------------------------------------


class TestTonneauOpen:
    def test_tonneau_open_sends_command(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/open_tonneau",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "tonneau-open"])

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "trunk.tonneau-open"
        assert parsed["data"]["response"]["result"] is True

    def test_tonneau_open_hits_correct_endpoint(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(json=CMD_OK)
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "tonneau-open"])

        assert result.exit_code == 0
        req_url = _request_url(httpx_mock)
        assert f"/api/1/vehicles/{VIN}/command/open_tonneau" in req_url


class TestTonneauClose:
    def test_tonneau_close_sends_command(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/close_tonneau",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "tonneau-close"])

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "trunk.tonneau-close"
        assert parsed["data"]["response"]["result"] is True


class TestTonneauStop:
    def test_tonneau_stop_sends_command(
        self, httpx_mock: HTTPXMock, cli_env: dict[str, str]
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/stop_tonneau",
            json=CMD_OK,
        )
        result = CliRunner().invoke(cli, ["--format", "json", "--wake", "trunk", "tonneau-stop"])

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "trunk.tonneau-stop"
        assert parsed["data"]["response"]["result"] is True
