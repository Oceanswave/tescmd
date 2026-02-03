"""Pydantic v2 models for the trigger/subscription system.

Triggers let OpenClaw bots and MCP clients register conditions on
telemetry fields and receive notifications when they fire.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TriggerOperator(StrEnum):
    """Supported comparison operators for trigger conditions."""

    LT = "lt"
    GT = "gt"
    LTE = "lte"
    GTE = "gte"
    EQ = "eq"
    NEQ = "neq"
    CHANGED = "changed"
    ENTER = "enter"
    LEAVE = "leave"


# Operators that require no threshold value
_NO_VALUE_OPS = frozenset({TriggerOperator.CHANGED})

# Geofence operators require a dict with lat/lon/radius
_GEOFENCE_OPS = frozenset({TriggerOperator.ENTER, TriggerOperator.LEAVE})


class TriggerCondition(BaseModel):
    """A single condition that a trigger evaluates.

    For most operators, ``value`` is a numeric or string threshold.
    For ``changed``, ``value`` is not required.
    For ``enter``/``leave``, ``value`` is a dict with
    ``latitude``, ``longitude``, and ``radius_m``.
    """

    field: str
    operator: TriggerOperator
    value: Any = None

    @model_validator(mode="after")
    def _validate_value_for_operator(self) -> TriggerCondition:
        op = self.operator
        if op in _GEOFENCE_OPS:
            if not isinstance(self.value, dict):
                raise ValueError(
                    f"Operator '{op.value}' requires a dict value "
                    "with latitude, longitude, radius_m"
                )
            missing = {"latitude", "longitude", "radius_m"} - set(self.value.keys())
            if missing:
                raise ValueError(f"Geofence value missing keys: {', '.join(sorted(missing))}")
        elif op not in _NO_VALUE_OPS and self.value is None:
            raise ValueError(f"Operator '{op.value}' requires a 'value' parameter")
        return self


def _make_trigger_id() -> str:
    """Generate a short hex ID (12 chars from a UUID4)."""
    return uuid.uuid4().hex[:12]


class TriggerDefinition(BaseModel):
    """A registered trigger with its condition and firing configuration."""

    id: str = Field(default_factory=_make_trigger_id)
    condition: TriggerCondition
    once: bool = False
    cooldown_seconds: float = Field(default=60.0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TriggerNotification(BaseModel):
    """Notification emitted when a trigger fires."""

    trigger_id: str
    field: str
    operator: TriggerOperator
    threshold: Any = None
    value: Any = None
    previous_value: Any = None
    fired_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    vin: str = ""
