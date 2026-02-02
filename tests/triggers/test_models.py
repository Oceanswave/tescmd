"""Tests for trigger/subscription Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tescmd.triggers.models import (
    TriggerCondition,
    TriggerDefinition,
    TriggerNotification,
    TriggerOperator,
)


class TestTriggerOperator:
    def test_all_operators_exist(self) -> None:
        ops = {e.value for e in TriggerOperator}
        assert ops == {"lt", "gt", "lte", "gte", "eq", "neq", "changed", "enter", "leave"}

    def test_from_string(self) -> None:
        assert TriggerOperator("lt") is TriggerOperator.LT
        assert TriggerOperator("changed") is TriggerOperator.CHANGED
        assert TriggerOperator("enter") is TriggerOperator.ENTER


class TestTriggerCondition:
    def test_basic_condition(self) -> None:
        c = TriggerCondition(field="BatteryLevel", operator=TriggerOperator.LT, value=20)
        assert c.field == "BatteryLevel"
        assert c.operator == TriggerOperator.LT
        assert c.value == 20

    def test_changed_no_value(self) -> None:
        c = TriggerCondition(field="Locked", operator=TriggerOperator.CHANGED)
        assert c.value is None

    def test_geofence_value(self) -> None:
        geo = {"latitude": 37.77, "longitude": -122.42, "radius_m": 500}
        c = TriggerCondition(field="Location", operator=TriggerOperator.ENTER, value=geo)
        assert c.value["radius_m"] == 500


class TestTriggerConditionValidator:
    """Tests for the @model_validator on TriggerCondition."""

    def test_numeric_op_requires_value(self) -> None:
        with pytest.raises(ValidationError, match="requires a 'value' parameter"):
            TriggerCondition(field="Soc", operator=TriggerOperator.LT)

    def test_eq_op_requires_value(self) -> None:
        with pytest.raises(ValidationError, match="requires a 'value' parameter"):
            TriggerCondition(field="ChargeState", operator=TriggerOperator.EQ)

    def test_neq_op_requires_value(self) -> None:
        with pytest.raises(ValidationError, match="requires a 'value' parameter"):
            TriggerCondition(field="Gear", operator=TriggerOperator.NEQ)

    def test_changed_op_does_not_require_value(self) -> None:
        c = TriggerCondition(field="Locked", operator=TriggerOperator.CHANGED)
        assert c.value is None

    def test_geofence_requires_dict(self) -> None:
        with pytest.raises(ValidationError, match="requires a dict value"):
            TriggerCondition(field="Location", operator=TriggerOperator.ENTER, value=42)

    def test_geofence_requires_all_keys(self) -> None:
        with pytest.raises(ValidationError, match="missing keys"):
            TriggerCondition(
                field="Location",
                operator=TriggerOperator.LEAVE,
                value={"latitude": 37.0},
            )

    def test_geofence_leave_requires_dict(self) -> None:
        with pytest.raises(ValidationError, match="requires a dict value"):
            TriggerCondition(field="Location", operator=TriggerOperator.LEAVE, value="home")

    def test_valid_geofence_passes(self) -> None:
        c = TriggerCondition(
            field="Location",
            operator=TriggerOperator.ENTER,
            value={"latitude": 37.77, "longitude": -122.42, "radius_m": 100},
        )
        assert c.operator == TriggerOperator.ENTER


class TestTriggerDefinition:
    def test_id_auto_generated(self) -> None:
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.LT, value=20)
        t = TriggerDefinition(condition=cond)
        assert len(t.id) == 12
        assert isinstance(t.id, str)

    def test_ids_are_unique(self) -> None:
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.LT, value=20)
        ids = {TriggerDefinition(condition=cond).id for _ in range(50)}
        assert len(ids) == 50

    def test_defaults(self) -> None:
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.LT, value=20)
        t = TriggerDefinition(condition=cond)
        assert t.once is False
        assert t.cooldown_seconds == 60.0
        assert isinstance(t.created_at, datetime)

    def test_once_flag(self) -> None:
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.LT, value=20)
        t = TriggerDefinition(condition=cond, once=True)
        assert t.once is True

    def test_custom_cooldown(self) -> None:
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.LT, value=20)
        t = TriggerDefinition(condition=cond, cooldown_seconds=30.0)
        assert t.cooldown_seconds == 30.0


class TestTriggerDefinitionValidation:
    """Tests for Field(ge=0) constraints on TriggerDefinition."""

    def test_negative_cooldown_rejected(self) -> None:
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.LT, value=20)
        with pytest.raises(ValidationError, match="cooldown_seconds"):
            TriggerDefinition(condition=cond, cooldown_seconds=-1.0)

    def test_zero_cooldown_allowed(self) -> None:
        cond = TriggerCondition(field="Soc", operator=TriggerOperator.LT, value=20)
        t = TriggerDefinition(condition=cond, cooldown_seconds=0)
        assert t.cooldown_seconds == 0


class TestTriggerNotification:
    def test_serialization(self) -> None:
        ts = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)
        n = TriggerNotification(
            trigger_id="abc123def456",
            field="BatteryLevel",
            operator="lt",
            threshold=20,
            value=18.5,
            previous_value=21.0,
            fired_at=ts,
            vin="VIN123",
        )
        data = n.model_dump(mode="json")
        assert data["trigger_id"] == "abc123def456"
        assert data["field"] == "BatteryLevel"
        assert data["operator"] == "lt"
        assert data["threshold"] == 20
        assert data["value"] == 18.5
        assert data["previous_value"] == 21.0
        assert data["vin"] == "VIN123"
        assert "fired_at" in data

    def test_defaults(self) -> None:
        n = TriggerNotification(trigger_id="x", field="f", operator="eq")
        assert n.threshold is None
        assert n.value is None
        assert n.previous_value is None
        assert n.vin == ""
