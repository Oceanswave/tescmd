"""Shared test fixtures for the tescmd test suite."""

from __future__ import annotations

from typing import Any

import pytest

from tescmd.api.client import TeslaFleetClient

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


@pytest.fixture
def mock_client() -> TeslaFleetClient:
    """Return a TeslaFleetClient configured for testing."""
    return TeslaFleetClient(access_token="test-token", region="na")


@pytest.fixture
def sample_vehicle_list_response() -> dict[str, Any]:
    """Return a sample /api/1/vehicles response payload."""
    return {
        "response": [
            {
                "vin": "5YJ3E1EA1NF000001",
                "display_name": "My Model 3",
                "state": "online",
                "vehicle_id": 123456,
                "access_type": "OWNER",
            }
        ],
        "count": 1,
    }


@pytest.fixture
def sample_vehicle_data_response() -> dict[str, Any]:
    """Return a sample /api/1/vehicles/{vin}/vehicle_data response payload."""
    return {
        "response": {
            "vin": "5YJ3E1EA1NF000001",
            "display_name": "My Model 3",
            "state": "online",
            "vehicle_id": 123456,
            "charge_state": {
                "battery_level": 72,
                "battery_range": 215.5,
                "charging_state": "Complete",
                "charge_limit_soc": 80,
            },
            "climate_state": {
                "inside_temp": 22.0,
                "outside_temp": 15.5,
                "is_climate_on": False,
            },
            "drive_state": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "heading": 180,
                "speed": None,
            },
            "vehicle_state": {
                "locked": True,
                "odometer": 12345.6,
                "sentry_mode": True,
                "car_version": "2024.8.9",
            },
        }
    }
