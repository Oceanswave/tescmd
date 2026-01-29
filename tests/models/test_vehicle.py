from __future__ import annotations

from tescmd.models.vehicle import (
    ChargeState,
    ClimateState,
    DriveState,
    Vehicle,
    VehicleData,
    VehicleState,
)


class TestVehicle:
    def test_basic(self) -> None:
        v = Vehicle(vin="5YJ3E1EA1NF000001")
        assert v.vin == "5YJ3E1EA1NF000001"
        assert v.display_name is None
        assert v.state == "unknown"
        assert v.vehicle_id is None
        assert v.access_type is None


class TestDriveState:
    def test_defaults(self) -> None:
        ds = DriveState()
        assert ds.latitude is None
        assert ds.longitude is None
        assert ds.heading is None
        assert ds.speed is None
        assert ds.power is None
        assert ds.shift_state is None
        assert ds.timestamp is None

    def test_with_values(self) -> None:
        ds = DriveState(latitude=37.7749, longitude=-122.4194, heading=90, speed=65)
        assert ds.latitude == 37.7749
        assert ds.longitude == -122.4194
        assert ds.heading == 90
        assert ds.speed == 65


class TestChargeState:
    def test_defaults(self) -> None:
        cs = ChargeState()
        assert cs.battery_level is None
        assert cs.charging_state is None

    def test_with_values(self) -> None:
        cs = ChargeState(battery_level=80, charging_state="Charging", charge_rate=32.0)
        assert cs.battery_level == 80
        assert cs.charging_state == "Charging"
        assert cs.charge_rate == 32.0


class TestClimateState:
    def test_defaults(self) -> None:
        cl = ClimateState()
        assert cl.inside_temp is None
        assert cl.is_climate_on is None

    def test_with_values(self) -> None:
        cl = ClimateState(inside_temp=22.5, outside_temp=15.0, is_climate_on=True)
        assert cl.inside_temp == 22.5
        assert cl.outside_temp == 15.0
        assert cl.is_climate_on is True


class TestVehicleState:
    def test_defaults(self) -> None:
        vs = VehicleState()
        assert vs.locked is None
        assert vs.odometer is None

    def test_with_values(self) -> None:
        vs = VehicleState(locked=True, odometer=12345.6, sentry_mode=False)
        assert vs.locked is True
        assert vs.odometer == 12345.6
        assert vs.sentry_mode is False


class TestVehicleData:
    def test_full(self) -> None:
        vd = VehicleData(
            vin="5YJ3E1EA1NF000001",
            display_name="My Tesla",
            state="online",
            vehicle_id=123456,
            charge_state=ChargeState(battery_level=90),
            climate_state=ClimateState(inside_temp=21.0),
            drive_state=DriveState(latitude=37.0),
            vehicle_state=VehicleState(locked=True),
        )
        assert vd.vin == "5YJ3E1EA1NF000001"
        assert vd.display_name == "My Tesla"
        assert vd.state == "online"
        assert vd.vehicle_id == 123456
        assert vd.charge_state is not None
        assert vd.charge_state.battery_level == 90
        assert vd.climate_state is not None
        assert vd.climate_state.inside_temp == 21.0
        assert vd.drive_state is not None
        assert vd.drive_state.latitude == 37.0
        assert vd.vehicle_state is not None
        assert vd.vehicle_state.locked is True

    def test_model_validate_raw_api_dict(self) -> None:
        """Simulate a raw API response dict with nested objects and extra fields."""
        raw: dict[str, object] = {
            "vin": "5YJ3E1EA1NF000001",
            "display_name": "Road Runner",
            "state": "online",
            "vehicle_id": 999,
            "charge_state": {
                "battery_level": 72,
                "charging_state": "Complete",
                "some_future_field": "ignored-by-us-but-kept",
            },
            "climate_state": {
                "inside_temp": 20.5,
                "outside_temp": 10.0,
            },
            "drive_state": {
                "latitude": 52.52,
                "longitude": 13.405,
                "native_location_supported": 1,
            },
            "vehicle_state": {
                "locked": False,
                "odometer": 54321.1,
                "tpms_pressure_fl": 2.9,
            },
            "vehicle_config": {
                "car_type": "modely",
                "exterior_color": "DeepBlue",
            },
            "gui_settings": {
                "gui_distance_units": "km/hr",
                "gui_temperature_units": "C",
            },
            "some_unknown_top_level": True,
        }
        vd = VehicleData.model_validate(raw)
        assert vd.vin == "5YJ3E1EA1NF000001"
        assert vd.display_name == "Road Runner"
        assert vd.charge_state is not None
        assert vd.charge_state.battery_level == 72
        assert vd.charge_state.charging_state == "Complete"
        assert vd.drive_state is not None
        assert vd.drive_state.latitude == 52.52
        assert vd.vehicle_state is not None
        assert vd.vehicle_state.locked is False
        assert vd.vehicle_config is not None
        assert vd.vehicle_config.car_type == "modely"
        assert vd.gui_settings is not None
        assert vd.gui_settings.gui_distance_units == "km/hr"
