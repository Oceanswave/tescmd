"""Execution tests for the energy CLI commands.

Each test mocks the Fleet API via ``httpx_mock`` (pytest-httpx), invokes the
Click CLI through ``CliRunner``, and asserts on the JSON output envelope.

Energy commands operate on *energy sites* (Powerwalls, Solar) identified by an
integer ``site_id`` rather than a vehicle VIN.  They do **not** require the
``--wake`` flag.
"""

from __future__ import annotations

import json

from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from tescmd.cli.main import cli

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
SITE_ID = 12345


# -- Reusable mock payloads ---------------------------------------------------

PRODUCTS_RESPONSE: dict = {
    "response": [
        {
            "energy_site_id": SITE_ID,
            "resource_type": "battery",
            "site_name": "My Powerwall",
            "gateway_id": "gw-001",
        },
        {
            "id": 999,
            "vehicle_id": 999,
            "display_name": "My Model 3",
            "state": "online",
        },
    ],
}

SITE_INFO_RESPONSE: dict = {
    "response": {
        "energy_site_id": SITE_ID,
        "site_name": "My Home",
        "resource_type": "battery",
        "backup_reserve_percent": 20.0,
        "default_real_mode": "self_consumption",
        "storm_mode_enabled": False,
        "installation_date": "2024-01-15",
    },
}

LIVE_STATUS_RESPONSE: dict = {
    "response": {
        "solar_power": 5000.0,
        "battery_power": -1000.0,
        "grid_power": 2000.0,
        "load_power": 6000.0,
        "grid_status": "Active",
        "battery_level": 80.0,
        "percentage_charged": 80.0,
    },
}

CALENDAR_HISTORY_RESPONSE: dict = {
    "response": {
        "serial_number": "abc123",
        "time_series": [
            {"timestamp": "2024-06-01T00:00:00Z", "solar_energy_exported": 25000},
            {"timestamp": "2024-06-02T00:00:00Z", "solar_energy_exported": 27000},
        ],
    },
}

CHARGING_HISTORY_RESPONSE: dict = {
    "response": {
        "serial_number": "ch-456",
        "time_series": [
            {"timestamp": "2024-06-01T00:00:00Z", "charge_energy": 12000},
        ],
    },
}

COMMAND_RESPONSE: dict = {
    "response": {"code": 200, "message": "Updated"},
}


# =============================================================================
# energy list
# =============================================================================


class TestEnergyList:
    """Tests for ``tescmd energy list`` (GET /api/1/products)."""

    def test_list_products(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/products",
            json=PRODUCTS_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "list"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.list"
        # energy list filters to products with energy_site_id
        assert len(parsed["data"]) == 1
        assert parsed["data"][0]["energy_site_id"] == SITE_ID
        assert parsed["data"][0]["site_name"] == "My Powerwall"

    def test_list_products_empty(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/products",
            json={"response": []},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "list"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.list"
        assert parsed["data"] == []

    def test_list_excludes_non_energy_products(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """Products without energy_site_id (vehicles) are filtered out."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/products",
            json={
                "response": [
                    {"id": 1, "vehicle_id": 1, "display_name": "Car", "state": "online"},
                ],
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "list"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["data"] == []


# =============================================================================
# energy status
# =============================================================================


class TestEnergyStatus:
    """Tests for ``tescmd energy status SITE_ID`` (GET site_info)."""

    def test_status_returns_site_info(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/site_info",
            json=SITE_INFO_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "status", str(SITE_ID)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.status"
        assert parsed["data"]["energy_site_id"] == SITE_ID
        assert parsed["data"]["site_name"] == "My Home"
        assert parsed["data"]["backup_reserve_percent"] == 20.0
        assert parsed["data"]["default_real_mode"] == "self_consumption"
        assert parsed["data"]["storm_mode_enabled"] is False

    def test_status_has_timestamp(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/site_info",
            json=SITE_INFO_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "status", str(SITE_ID)],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed


# =============================================================================
# energy live
# =============================================================================


class TestEnergyLive:
    """Tests for ``tescmd energy live SITE_ID`` (GET live_status)."""

    def test_live_returns_power_flow(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/live_status",
            json=LIVE_STATUS_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "live", str(SITE_ID)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.live"
        assert parsed["data"]["solar_power"] == 5000.0
        assert parsed["data"]["battery_power"] == -1000.0
        assert parsed["data"]["grid_power"] == 2000.0
        assert parsed["data"]["load_power"] == 6000.0
        assert parsed["data"]["grid_status"] == "Active"
        assert parsed["data"]["battery_level"] == 80.0


# =============================================================================
# energy backup
# =============================================================================


class TestEnergyBackup:
    """Tests for ``tescmd energy backup SITE_ID PERCENT`` (POST backup)."""

    def test_backup_set_reserve(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/backup",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "backup", str(SITE_ID), "50"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.backup"
        assert parsed["data"]["code"] == 200

    def test_backup_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/backup",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "energy", "backup", str(SITE_ID), "75"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        post_req = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_req.content)
        assert body["backup_reserve_percent"] == 75

    def test_backup_rejects_out_of_range(self) -> None:
        """backup rejects values outside 0-100."""
        runner = CliRunner()
        result = runner.invoke(cli, ["energy", "backup", "12345", "150"])
        assert result.exit_code != 0


# =============================================================================
# energy mode
# =============================================================================


class TestEnergyMode:
    """Tests for ``tescmd energy mode SITE_ID MODE`` (POST operation)."""

    def test_mode_self_consumption(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/operation",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "mode", str(SITE_ID), "self_consumption"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.mode"
        assert parsed["data"]["code"] == 200

    def test_mode_backup(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/operation",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "mode", str(SITE_ID), "backup"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.mode"

    def test_mode_autonomous(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/operation",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "mode", str(SITE_ID), "autonomous"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.mode"

    def test_mode_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/operation",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "energy", "mode", str(SITE_ID), "autonomous"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        post_req = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_req.content)
        assert body["default_real_mode"] == "autonomous"

    def test_mode_rejects_invalid_choice(self) -> None:
        """mode rejects values not in {self_consumption, backup, autonomous}."""
        runner = CliRunner()
        result = runner.invoke(cli, ["energy", "mode", "12345", "invalid"])
        assert result.exit_code != 0


# =============================================================================
# energy storm
# =============================================================================


class TestEnergyStorm:
    """Tests for ``tescmd energy storm SITE_ID --on/--off`` (POST storm_mode)."""

    def test_storm_enable(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/storm_mode",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "storm", str(SITE_ID), "--on"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.storm"
        assert parsed["data"]["code"] == 200

    def test_storm_disable(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/storm_mode",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "storm", str(SITE_ID), "--off"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.storm"

    def test_storm_enable_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/storm_mode",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "energy", "storm", str(SITE_ID), "--on"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        post_req = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_req.content)
        assert body["enabled"] is True

    def test_storm_disable_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/storm_mode",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "energy", "storm", str(SITE_ID), "--off"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        post_req = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_req.content)
        assert body["enabled"] is False


# =============================================================================
# energy tou
# =============================================================================


class TestEnergyTou:
    """Tests for ``tescmd energy tou SITE_ID SETTINGS_JSON`` (POST time_of_use_settings)."""

    def test_tou_update(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/time_of_use_settings",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        settings = json.dumps({"peak": {"start": "16:00", "end": "21:00"}})
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "tou", str(SITE_ID), settings],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.tou"
        assert parsed["data"]["code"] == 200

    def test_tou_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/time_of_use_settings",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        tou_settings = {"peak": {"start": "16:00", "end": "21:00"}}
        settings_json = json.dumps(tou_settings)
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "energy", "tou", str(SITE_ID), settings_json],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        post_req = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_req.content)
        assert body["tou_settings"] == tou_settings


# =============================================================================
# energy history
# =============================================================================


class TestEnergyHistory:
    """Tests for ``tescmd energy history SITE_ID`` (GET history?kind=charging)."""

    def test_history_returns_data(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/history?kind=charging",
            json=CHARGING_HISTORY_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "history", str(SITE_ID)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.history"
        assert parsed["data"]["serial_number"] == "ch-456"
        assert len(parsed["data"]["time_series"]) == 1

    def test_history_empty_time_series(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/history?kind=charging",
            json={"response": {"serial_number": "ch-789", "time_series": []}},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "history", str(SITE_ID)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["data"]["serial_number"] == "ch-789"
        assert parsed["data"]["time_series"] == []


# =============================================================================
# energy off-grid
# =============================================================================


class TestEnergyOffGrid:
    """Tests for ``tescmd energy off-grid SITE_ID RESERVE`` (POST off_grid)."""

    def test_off_grid_set_reserve(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/off_grid_vehicle_charging_reserve",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "off-grid", str(SITE_ID), "60"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.off-grid"
        assert parsed["data"]["code"] == 200

    def test_off_grid_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/off_grid_vehicle_charging_reserve",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "energy", "off-grid", str(SITE_ID), "45"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        post_req = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_req.content)
        assert body["off_grid_vehicle_charging_reserve_percent"] == 45

    def test_off_grid_rejects_out_of_range(self) -> None:
        """off-grid rejects values outside 0-100."""
        runner = CliRunner()
        result = runner.invoke(cli, ["energy", "off-grid", "12345", "150"])
        assert result.exit_code != 0


# =============================================================================
# energy grid-config
# =============================================================================


class TestEnergyGridConfig:
    """Tests for ``tescmd energy grid-config SITE_ID CONFIG_JSON`` (POST grid_import_export)."""

    def test_grid_config_update(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/grid_import_export",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        config = json.dumps({
            "disallow_charge_from_grid_with_solar_installed": True,
            "customer_preferred_export_rule": "pv_only",
        })
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "grid-config", str(SITE_ID), config],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.grid-config"
        assert parsed["data"]["code"] == 200

    def test_grid_config_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/grid_import_export",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        grid_config = {
            "disallow_charge_from_grid_with_solar_installed": False,
            "customer_preferred_export_rule": "battery_ok",
        }
        config_json = json.dumps(grid_config)
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "energy", "grid-config", str(SITE_ID), config_json],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        post_req = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_req.content)
        # grid_import_export sends the config dict directly as the POST body
        assert body == grid_config


# =============================================================================
# energy calendar
# =============================================================================


class TestEnergyCalendar:
    """Tests for ``tescmd energy calendar SITE_ID`` (GET calendar_history)."""

    def test_calendar_defaults(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """calendar with default options (kind=energy, period=day)."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/calendar_history?kind=energy&period=day",
            json=CALENDAR_HISTORY_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "calendar", str(SITE_ID)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.calendar"
        assert parsed["data"]["serial_number"] == "abc123"
        assert len(parsed["data"]["time_series"]) == 2

    def test_calendar_with_kind_and_period(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """calendar with explicit kind=backup and period=month."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/calendar_history?kind=backup&period=month",
            json=CALENDAR_HISTORY_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--format", "json",
                "energy", "calendar", str(SITE_ID),
                "--kind", "backup",
                "--period", "month",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "energy.calendar"

    def test_calendar_sends_correct_params(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """Verify query parameters are sent correctly."""
        httpx_mock.add_response(
            json=CALENDAR_HISTORY_RESPONSE,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "--format", "json",
                "energy", "calendar", str(SITE_ID),
                "--kind", "backup",
                "--period", "week",
            ],
            catch_exceptions=False,
        )
        request = httpx_mock.get_requests()[0]
        assert "kind=backup" in str(request.url)
        assert "period=week" in str(request.url)

    def test_calendar_with_date_range(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """calendar with --start-date and --end-date options."""
        httpx_mock.add_response(
            json=CALENDAR_HISTORY_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--format", "json",
                "energy", "calendar", str(SITE_ID),
                "--kind", "energy",
                "--period", "day",
                "--start-date", "2024-06-01",
                "--end-date", "2024-06-30",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        request = httpx_mock.get_requests()[0]
        assert "start_date=2024-06-01" in str(request.url)
        assert "end_date=2024-06-30" in str(request.url)

    def test_calendar_empty_time_series(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/calendar_history?kind=energy&period=day",
            json={"response": {"serial_number": "empty-001", "time_series": []}},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "calendar", str(SITE_ID)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["data"]["time_series"] == []


# =============================================================================
# Output envelope structure
# =============================================================================


class TestOutputEnvelope:
    """Verify the JSON envelope structure shared by energy commands."""

    def test_envelope_has_timestamp(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/products",
            json=PRODUCTS_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "list"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed

    def test_post_envelope_contains_response(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/energy_sites/{SITE_ID}/backup",
            method="POST",
            json=COMMAND_RESPONSE,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "energy", "backup", str(SITE_ID), "50"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert parsed["data"]["code"] == 200
        assert parsed["data"]["message"] == "Updated"
