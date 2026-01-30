"""Execution tests for the user CLI commands.

Each test mocks the Fleet API via ``httpx_mock`` (pytest-httpx), invokes the
Click CLI through ``CliRunner``, and asserts on the JSON output envelope.

User commands do not require a VIN or ``--wake`` flag — they operate on the
authenticated user's account directly.
"""

from __future__ import annotations

import json

from click.testing import CliRunner
from pytest_httpx import HTTPXMock

from tescmd.cli.main import cli

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"


# =============================================================================
# user me
# =============================================================================


class TestUserMe:
    """Tests for ``tescmd user me``."""

    def test_me_returns_profile(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """user me returns the account profile in the JSON envelope."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/users/me",
            method="GET",
            json={
                "response": {
                    "email": "test@example.com",
                    "full_name": "Test User",
                    "profile_image_url": None,
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "user", "me"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "user.me"
        assert parsed["data"]["email"] == "test@example.com"
        assert parsed["data"]["full_name"] == "Test User"
        # profile_image_url is None so it should be excluded by model_dump(exclude_none=True)
        assert "profile_image_url" not in parsed["data"]

    def test_me_envelope_has_timestamp(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """user me JSON envelope contains a timestamp field."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/users/me",
            method="GET",
            json={
                "response": {
                    "email": "test@example.com",
                    "full_name": "Test User",
                    "profile_image_url": None,
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "user", "me"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "timestamp" in parsed


# =============================================================================
# user region
# =============================================================================


class TestUserRegion:
    """Tests for ``tescmd user region``."""

    def test_region_returns_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """user region returns the regional Fleet API base URL."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/users/region",
            method="GET",
            json={
                "response": {
                    "region": "NA",
                    "fleet_api_base_url": "https://fleet-api.prd.na.vn.cloud.tesla.com",
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "user", "region"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "user.region"
        assert parsed["data"]["region"] == "NA"
        assert parsed["data"]["fleet_api_base_url"] == "https://fleet-api.prd.na.vn.cloud.tesla.com"


# =============================================================================
# user orders
# =============================================================================


class TestUserOrders:
    """Tests for ``tescmd user orders``."""

    def test_orders_returns_list(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """user orders returns a list of vehicle orders."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/users/orders",
            method="GET",
            json={
                "response": [
                    {
                        "order_id": "RN123",
                        "vin": None,
                        "model": "Model Y",
                        "status": "ORDERED",
                    }
                ]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "user", "orders"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "user.orders"
        assert isinstance(parsed["data"], list)
        assert len(parsed["data"]) == 1
        assert parsed["data"][0]["order_id"] == "RN123"
        assert parsed["data"][0]["model"] == "Model Y"
        assert parsed["data"][0]["status"] == "ORDERED"
        # vin is None so it should be excluded by model_dump(exclude_none=True)
        assert "vin" not in parsed["data"][0]

    def test_orders_empty_list(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """user orders returns an empty list when there are no orders."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/users/orders",
            method="GET",
            json={"response": []},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "user", "orders"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "user.orders"
        assert parsed["data"] == []


# =============================================================================
# user features
# =============================================================================


class TestUserFeatures:
    """Tests for ``tescmd user features``."""

    def test_features_returns_config(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """user features returns the feature flags configuration."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/users/feature_config",
            method="GET",
            json={"response": {"signaling": {"enabled": True}}},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "user", "features"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "user.features"
        assert parsed["data"]["signaling"] == {"enabled": True}
