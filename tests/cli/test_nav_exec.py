"""Execution tests for the nav CLI commands.

Each test mocks the Fleet API via ``httpx_mock`` (pytest-httpx), invokes the
Click CLI through ``CliRunner``, and asserts on the JSON output envelope.

Navigation commands use ``execute_command()`` (for send, gps, supercharger,
waypoints) or ``get_command_api()`` directly (homelink).  All mock POSTs go to
``/api/1/vehicles/{vin}/command/{method}``.
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


def _request_body(httpx_mock: HTTPXMock, idx: int = 0) -> dict[str, Any]:
    """Parse the JSON body of the idx-th captured request."""
    return json.loads(httpx_mock.get_requests()[idx].content)  # type: ignore[no-any-return]


# =============================================================================
# nav send
# =============================================================================


class TestNavSend:
    """Tests for ``tescmd nav send VIN ADDRESS...``."""

    def test_nav_send(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav send posts to /command/share and returns success."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/share",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "send", VIN, "123", "Main", "St"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "nav.send"
        assert parsed["data"]["response"]["result"] is True

    def test_nav_send_joins_address_words(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav send joins multi-word address into a single string."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/share",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "--format", "json", "--wake",
                "nav", "send", VIN,
                "1600", "Amphitheatre", "Parkway", "Mountain", "View", "CA",
            ],
            catch_exceptions=False,
        )
        body = _request_body(httpx_mock)
        # The share method wraps the address in the android.intent.extra.TEXT value
        assert "1600 Amphitheatre Parkway Mountain View CA" in json.dumps(body)

    def test_nav_send_has_timestamp(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/share",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "send", VIN, "123", "Main", "St"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed


# =============================================================================
# nav gps
# =============================================================================


class TestNavGps:
    """Tests for ``tescmd nav gps VIN LAT LON``.

    Note: Click treats negative numbers (e.g. ``-122.4``) as option flags, so
    tests use positive longitudes to avoid that parsing limitation.
    """

    def test_nav_gps(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav gps posts to /command/navigation_gps_request and returns success."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/navigation_gps_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "gps", VIN, "37.7749", "122.4194"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "nav.gps"
        assert parsed["data"]["response"]["result"] is True

    def test_nav_gps_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav gps sends lat, lon, and order in the request body."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/navigation_gps_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "gps", VIN, "40.7128", "74.0060"],
            catch_exceptions=False,
        )
        body = _request_body(httpx_mock)
        assert body["lat"] == 40.7128
        assert body["lon"] == 74.006


# =============================================================================
# nav supercharger
# =============================================================================


class TestNavSupercharger:
    """Tests for ``tescmd nav supercharger``."""

    def test_nav_supercharger(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav supercharger posts to /command/navigation_sc_request."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/navigation_sc_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "supercharger"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "nav.supercharger"
        assert parsed["data"]["response"]["result"] is True

    def test_nav_supercharger_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav supercharger sends POST to navigation_sc_request endpoint."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/navigation_sc_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "supercharger"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "navigation_sc_request" in str(requests[0].url)
        assert requests[0].method == "POST"


# =============================================================================
# nav homelink
# =============================================================================


class TestNavHomelink:
    """Tests for ``tescmd nav homelink --lat LAT --lon LON``."""

    def test_nav_homelink_with_coords(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav homelink --lat/--lon posts to /command/trigger_homelink."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/trigger_homelink",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--format", "json", "--wake",
                "nav", "homelink",
                "--lat", "37.77", "--lon", "-122.42",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "nav.homelink"

    def test_nav_homelink_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav homelink sends lat and lon in the request body."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/trigger_homelink",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "--format", "json", "--wake",
                "nav", "homelink",
                "--lat", "37.77", "--lon", "-122.42",
            ],
            catch_exceptions=False,
        )
        body = _request_body(httpx_mock)
        assert body["lat"] == 37.77
        assert body["lon"] == -122.42

    def test_nav_homelink_auto_detects_location(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav homelink without --lat/--lon fetches vehicle drive_state first."""
        # First request: vehicle_data for drive_state coords
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/vehicle_data?endpoints=drive_state",
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "drive_state": {
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "heading": 180,
                    },
                },
            },
        )
        # Second request: trigger_homelink command
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/trigger_homelink",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "homelink"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "nav.homelink"

        # Verify two requests: GET vehicle_data then POST trigger_homelink
        requests = httpx_mock.get_requests()
        assert len(requests) == 2
        assert requests[0].method == "GET"
        assert "vehicle_data" in str(requests[0].url)
        assert requests[1].method == "POST"
        assert "trigger_homelink" in str(requests[1].url)


# =============================================================================
# nav waypoints
# =============================================================================


class TestNavWaypoints:
    """Tests for ``tescmd nav waypoints VIN WAYPOINTS_JSON``."""

    def test_nav_waypoints(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav waypoints posts to /command/navigation_request and returns success."""
        # navigation_waypoints_request maps to /command/navigation_request
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/navigation_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        waypoints_json = json.dumps([
            {"lat": 37.77, "lon": -122.42},
            {"lat": 37.33, "lon": -121.89},
        ])
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "waypoints", VIN, waypoints_json],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "nav.waypoints"
        assert parsed["data"]["response"]["result"] is True

    def test_nav_waypoints_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """nav waypoints sends waypoints list in the request body."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/navigation_request",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        waypoints_data = [{"lat": 40.71, "lon": -74.01}]
        waypoints_json = json.dumps(waypoints_data)
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "nav", "waypoints", VIN, waypoints_json],
            catch_exceptions=False,
        )
        body = _request_body(httpx_mock)
        assert "waypoints" in body
        assert body["waypoints"] == waypoints_data
