from __future__ import annotations

from tescmd.models.user import FeatureConfig, VehicleOrder


class TestVehicleOrder:
    def test_all_fields(self) -> None:
        order = VehicleOrder(
            order_id="ORD1",
            vin="5YJ3E1EA1NF000001",
            model="model3",
            status="delivered",
        )
        assert order.order_id == "ORD1"
        assert order.vin == "5YJ3E1EA1NF000001"
        assert order.model == "model3"
        assert order.status == "delivered"

    def test_extra_fields_captured(self) -> None:
        order = VehicleOrder(
            order_id="ORD1",
            vin="5YJ3E1EA1NF000001",
            model="model3",
            status="delivered",
            delivery_date="2024-06-15",  # type: ignore[call-arg]
        )
        assert order.order_id == "ORD1"
        assert order.model_extra is not None
        assert order.model_extra["delivery_date"] == "2024-06-15"

    def test_defaults_none(self) -> None:
        order = VehicleOrder()
        assert order.order_id is None
        assert order.vin is None
        assert order.model is None
        assert order.status is None


class TestFeatureConfig:
    def test_with_signaling(self) -> None:
        fc = FeatureConfig(signaling={"ble": True, "lte": False})
        assert fc.signaling is not None
        assert fc.signaling["ble"] is True
        assert fc.signaling["lte"] is False

    def test_extra_fields_captured(self) -> None:
        fc = FeatureConfig(
            signaling={"ble": True},
            experimental_flag="on",  # type: ignore[call-arg]
        )
        assert fc.signaling == {"ble": True}
        assert fc.model_extra is not None
        assert fc.model_extra["experimental_flag"] == "on"

    def test_defaults_none(self) -> None:
        fc = FeatureConfig()
        assert fc.signaling is None
