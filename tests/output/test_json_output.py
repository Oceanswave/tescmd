from __future__ import annotations

import json

from tescmd.models.vehicle import ChargeState, DriveState, Vehicle, VehicleData
from tescmd.output.json_output import format_json_error, format_json_response


class TestFormatJsonResponse:
    """Tests for :func:`format_json_response`."""

    def test_with_model(self) -> None:
        vehicle = Vehicle(vin="5YJ3E1EA1NF000001", display_name="My Tesla", state="online")
        raw = format_json_response(data=vehicle, command="vehicle.list")
        parsed = json.loads(raw)

        assert parsed["ok"] is True
        assert parsed["command"] == "vehicle.list"
        assert parsed["data"]["vin"] == "5YJ3E1EA1NF000001"
        assert parsed["data"]["display_name"] == "My Tesla"
        assert parsed["data"]["state"] == "online"
        assert "timestamp" in parsed

    def test_with_list_of_models(self) -> None:
        vehicles = [
            Vehicle(vin="5YJ3E1EA1NF000001", state="online"),
            Vehicle(vin="5YJ3E1EA1NF000002", state="asleep"),
        ]
        raw = format_json_response(data=vehicles, command="vehicle.list")
        parsed = json.loads(raw)

        assert parsed["ok"] is True
        assert isinstance(parsed["data"], list)
        assert len(parsed["data"]) == 2
        assert parsed["data"][0]["vin"] == "5YJ3E1EA1NF000001"
        assert parsed["data"][1]["state"] == "asleep"

    def test_with_dict(self) -> None:
        data = {"key": "value", "count": 42}
        raw = format_json_response(data=data, command="raw.get")
        parsed = json.loads(raw)

        assert parsed["ok"] is True
        assert parsed["data"] == {"key": "value", "count": 42}

    def test_nested_model(self) -> None:
        vd = VehicleData(
            vin="5YJ3E1EA1NF000001",
            charge_state=ChargeState(battery_level=72, charging_state="Complete"),
            drive_state=DriveState(latitude=37.394, longitude=-122.150),
        )
        raw = format_json_response(data=vd, command="vehicle.data")
        parsed = json.loads(raw)

        assert parsed["data"]["charge_state"]["battery_level"] == 72
        assert parsed["data"]["drive_state"]["latitude"] == 37.394
        # None fields should be excluded
        assert "climate_state" not in parsed["data"]

    def test_excludes_none_fields(self) -> None:
        vehicle = Vehicle(vin="5YJ3E1EA1NF000001")
        raw = format_json_response(data=vehicle, command="vehicle.list")
        parsed = json.loads(raw)

        # display_name is None so must be absent
        assert "display_name" not in parsed["data"]
        # state has a default ("unknown") so it is present
        assert parsed["data"]["state"] == "unknown"

    def test_timestamp_is_iso_utc(self) -> None:
        raw = format_json_response(data={"x": 1}, command="test")
        parsed = json.loads(raw)
        ts = parsed["timestamp"]
        # Should contain a UTC offset indicator
        assert "+" in ts or ts.endswith("Z") or "+00:00" in ts

    def test_dict_with_nested_model_is_serialized(self) -> None:
        """A plain dict containing a Pydantic model should serialize the model."""
        cs = ChargeState(battery_level=72, charging_state="Complete")
        data = {"response": cs, "extra": "info"}
        raw = format_json_response(data=data, command="test")
        parsed = json.loads(raw)

        assert isinstance(parsed["data"]["response"], dict)
        assert parsed["data"]["response"]["battery_level"] == 72
        assert parsed["data"]["response"]["charging_state"] == "Complete"
        assert parsed["data"]["extra"] == "info"

    def test_deeply_nested_dict_with_models(self) -> None:
        """Nested dicts at multiple depths with Pydantic models are serialized."""
        ds = DriveState(latitude=37.7, longitude=-122.4)
        data = {"level1": {"level2": {"drive": ds}}}
        raw = format_json_response(data=data, command="test")
        parsed = json.loads(raw)

        assert parsed["data"]["level1"]["level2"]["drive"]["latitude"] == 37.7

    def test_list_inside_dict_with_models(self) -> None:
        """A list inside a dict containing Pydantic models is serialized."""
        vehicles = [
            Vehicle(vin="VIN1", state="online"),
            Vehicle(vin="VIN2", state="asleep"),
        ]
        data = {"vehicles": vehicles, "count": 2}
        raw = format_json_response(data=data, command="test")
        parsed = json.loads(raw)

        assert len(parsed["data"]["vehicles"]) == 2
        assert parsed["data"]["vehicles"][0]["vin"] == "VIN1"
        assert parsed["data"]["count"] == 2


class TestFormatJsonError:
    """Tests for :func:`format_json_error`."""

    def test_basic_error(self) -> None:
        raw = format_json_error(
            code="AUTH_FAILED", message="Token expired", command="vehicle.list"
        )
        parsed = json.loads(raw)

        assert parsed["ok"] is False
        assert parsed["command"] == "vehicle.list"
        assert parsed["error"]["code"] == "AUTH_FAILED"
        assert parsed["error"]["message"] == "Token expired"
        assert "timestamp" in parsed

    def test_extra_fields(self) -> None:
        raw = format_json_error(
            code="RATE_LIMIT",
            message="Too many requests",
            command="vehicle.wake",
            retry_after=30,
        )
        parsed = json.loads(raw)

        assert parsed["error"]["retry_after"] == 30
        assert parsed["error"]["code"] == "RATE_LIMIT"
