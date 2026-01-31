"""Tests for the security CLI commands -- full execution with mocked HTTP responses."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"
CMD_OK = {"response": {"result": True, "reason": ""}}


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
# security status (read command -- GET vehicle_data?endpoints=vehicle_state)
# ---------------------------------------------------------------------------


class TestSecurityStatus:
    def test_status_returns_vehicle_state(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "vehicle_state": {
                        "locked": True,
                        "odometer": 15000.5,
                        "sentry_mode": False,
                        "car_version": "2024.26.9",
                        "df": 0,
                        "pf": 0,
                        "dr": 0,
                        "pr": 0,
                    },
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "status", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.status"
        assert parsed["data"]["locked"] is True
        assert parsed["data"]["sentry_mode"] is False
        assert parsed["data"]["odometer"] == 15000.5
        assert parsed["data"]["car_version"] == "2024.26.9"

    def test_status_sends_vehicle_state_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "vin": VIN,
                    "state": "online",
                    "vehicle_state": {
                        "locked": True,
                        "odometer": 15000.5,
                        "sentry_mode": False,
                        "car_version": "2024.26.9",
                    },
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "status", VIN],
            catch_exceptions=False,
        )
        request = httpx_mock.get_requests()[0]
        assert "endpoints=vehicle_state" in str(request.url)


# ---------------------------------------------------------------------------
# security lock
# ---------------------------------------------------------------------------


class TestSecurityLock:
    def test_lock_sends_command(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/door_lock",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "lock", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.lock"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security unlock
# ---------------------------------------------------------------------------


class TestSecurityUnlock:
    def test_unlock_sends_command(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/door_unlock",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "unlock", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.unlock"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security sentry
# ---------------------------------------------------------------------------


class TestSecuritySentry:
    def test_sentry_on(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_sentry_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "sentry", "--on", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.sentry"
        body = _cmd_request(httpx_mock, "set_sentry_mode")
        assert body["on"] is True

    def test_sentry_off(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_sentry_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "sentry", "--off", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        body = _cmd_request(httpx_mock, "set_sentry_mode")
        assert body["on"] is False


# ---------------------------------------------------------------------------
# security valet
# ---------------------------------------------------------------------------


class TestSecurityValet:
    def test_valet_on(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_valet_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "valet", "--on", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.valet"
        body = _cmd_request(httpx_mock, "set_valet_mode")
        assert body["on"] is True

    def test_valet_on_with_password(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_valet_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--format",
                "json",
                "--wake",
                "security",
                "valet",
                "--on",
                "--password",
                "1234",
                VIN,
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "set_valet_mode")
        assert body["on"] is True
        assert body["password"] == "1234"

    def test_valet_off(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_valet_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "valet", "--off", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "set_valet_mode")
        assert body["on"] is False


# ---------------------------------------------------------------------------
# security valet-reset
# ---------------------------------------------------------------------------


class TestSecurityValetReset:
    def test_valet_reset_sends_command(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/reset_valet_pin",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "valet-reset", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.valet-reset"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security remote-start
# ---------------------------------------------------------------------------


class TestSecurityRemoteStart:
    def test_remote_start_sends_command(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_start_drive",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "remote-start", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.remote-start"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security flash
# ---------------------------------------------------------------------------


class TestSecurityFlash:
    def test_flash_sends_command(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/flash_lights",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "flash", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.flash"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security honk
# ---------------------------------------------------------------------------


class TestSecurityHonk:
    def test_honk_sends_command(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/honk_horn",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "honk", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.honk"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security pin-reset
# ---------------------------------------------------------------------------


class TestSecurityPinReset:
    def test_pin_reset_sends_command(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/reset_pin_to_drive_pin",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "pin-reset", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.pin-reset"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security pin-clear-admin
# ---------------------------------------------------------------------------


class TestSecurityPinClearAdmin:
    def test_pin_clear_admin_sends_command(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/clear_pin_to_drive_admin",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "pin-clear-admin", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.pin-clear-admin"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security speed-clear
# ---------------------------------------------------------------------------


class TestSecuritySpeedClear:
    def test_speed_clear_sends_pin(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/speed_limit_clear_pin",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "speed-clear", "--pin", "1234", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.speed-clear"
        body = _cmd_request(httpx_mock, "speed_limit_clear_pin")
        assert body["pin"] == "1234"


# ---------------------------------------------------------------------------
# security speed-clear-admin
# ---------------------------------------------------------------------------


class TestSecuritySpeedClearAdmin:
    def test_speed_clear_admin_sends_command(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/speed_limit_clear_pin_admin",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "speed-clear-admin", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.speed-clear-admin"
        assert parsed["data"]["response"]["result"] is True


# ---------------------------------------------------------------------------
# security speed-limit (--activate, --deactivate, --set)
# ---------------------------------------------------------------------------


class TestSecuritySpeedLimit:
    def test_speed_limit_activate(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/speed_limit_activate",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "speed-limit", "--activate", "1234", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.speed-limit.activate"
        body = _cmd_request(httpx_mock, "speed_limit_activate")
        assert body["pin"] == "1234"

    def test_speed_limit_deactivate(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/speed_limit_deactivate",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--format",
                "json",
                "--wake",
                "security",
                "speed-limit",
                "--deactivate",
                "1234",
                VIN,
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.speed-limit.deactivate"
        body = _cmd_request(httpx_mock, "speed_limit_deactivate")
        assert body["pin"] == "1234"

    def test_speed_limit_set(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/speed_limit_set_limit",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "speed-limit", "--set", "65", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.speed-limit.set"
        body = _cmd_request(httpx_mock, "speed_limit_set_limit")
        assert body["limit_mph"] == 65

    def test_speed_limit_set_float(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """--set accepts float values for precision (e.g. 65.5 MPH)."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/speed_limit_set_limit",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "speed-limit", "--set", "65.5", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "speed_limit_set_limit")
        assert body["limit_mph"] == 65.5


# ---------------------------------------------------------------------------
# security pin-to-drive
# ---------------------------------------------------------------------------


class TestSecurityPinToDrive:
    def test_pin_to_drive_on(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_pin_to_drive",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "pin-to-drive", "--on", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.pin-to-drive"
        body = _cmd_request(httpx_mock, "set_pin_to_drive")
        assert body["on"] is True

    def test_pin_to_drive_off(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/set_pin_to_drive",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "pin-to-drive", "--off", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "set_pin_to_drive")
        assert body["on"] is False


# ---------------------------------------------------------------------------
# security guest-mode
# ---------------------------------------------------------------------------


class TestSecurityGuestMode:
    def test_guest_mode_on(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/guest_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "guest-mode", "--on", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.guest-mode"
        body = _cmd_request(httpx_mock, "guest_mode")
        assert body["enable"] is True

    def test_guest_mode_off(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/guest_mode",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "guest-mode", "--off", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "guest_mode")
        assert body["enable"] is False


# ---------------------------------------------------------------------------
# security boombox
# ---------------------------------------------------------------------------


class TestSecurityBoombox:
    def test_boombox_default_locate(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """Default --sound is locate (sound=2000)."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_boombox",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "boombox", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "security.boombox"
        assert parsed["data"]["response"]["result"] is True
        body = _cmd_request(httpx_mock, "remote_boombox")
        assert body["sound"] == 2000

    def test_boombox_fart_sound(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """--sound fart sends sound=0."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_boombox",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "boombox", "--sound", "fart", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "remote_boombox")
        assert body["sound"] == 0

    def test_boombox_locate_sound(self, cli_env: dict[str, str], httpx_mock: HTTPXMock) -> None:
        """--sound locate sends sound=2000."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/remote_boombox",
            json=CMD_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "security", "boombox", "--sound", "locate", VIN],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        body = _cmd_request(httpx_mock, "remote_boombox")
        assert body["sound"] == 2000
