"""Trigger evaluation engine.

Evaluates registered triggers against incoming telemetry values,
manages cooldowns, fires callbacks, and queues notifications.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from tescmd.triggers.models import (
    TriggerCondition,
    TriggerDefinition,
    TriggerNotification,
    TriggerOperator,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

logger = logging.getLogger(__name__)

MAX_TRIGGERS = 100


class TriggerLimitError(Exception):
    """Raised when the maximum number of triggers is exceeded."""


class TriggerManager:
    """Manages trigger lifecycle and evaluation.

    Parameters
    ----------
    vin:
        Vehicle Identification Number — included in notifications.
    """

    def __init__(self, vin: str) -> None:
        self._vin = vin
        self._triggers: dict[str, TriggerDefinition] = {}
        self._field_index: dict[str, set[str]] = defaultdict(set)
        self._last_fire_times: dict[str, float] = {}
        self._on_fire_callbacks: list[Callable[[TriggerNotification], Awaitable[None]]] = []
        self._fired_once_ids: set[str] = set()

    def create(self, trigger: TriggerDefinition) -> TriggerDefinition:
        """Register a trigger.  Returns the trigger with its assigned ID.

        Raises :class:`TriggerLimitError` if the limit is reached.
        """
        if len(self._triggers) >= MAX_TRIGGERS:
            raise TriggerLimitError(
                f"Maximum of {MAX_TRIGGERS} triggers reached. "
                "Delete some before creating new ones."
            )

        cond = trigger.condition
        self._triggers[trigger.id] = trigger
        self._field_index[cond.field].add(trigger.id)
        logger.info(
            "Created trigger %s: %s %s %s",
            trigger.id,
            cond.field,
            cond.operator.value,
            cond.value,
        )
        return trigger

    def delete(self, trigger_id: str) -> bool:
        """Remove a trigger by ID.  Returns ``True`` if it existed."""
        trigger = self._triggers.pop(trigger_id, None)
        if trigger is None:
            return False
        field = trigger.condition.field
        ids = self._field_index.get(field)
        if ids is not None:
            ids.discard(trigger_id)
            if not ids:
                del self._field_index[field]
        self._last_fire_times.pop(trigger_id, None)
        self._fired_once_ids.discard(trigger_id)
        logger.info("Deleted trigger %s", trigger_id)
        return True

    def list_all(self) -> list[TriggerDefinition]:
        """Return all registered triggers."""
        return list(self._triggers.values())

    @property
    def vin(self) -> str:
        """Vehicle Identification Number included in notifications."""
        return self._vin

    def mark_fired_once(self, trigger_id: str) -> None:
        """Mark a one-shot trigger as fired (pending delivery).

        The trigger stays in ``list_all()`` but is skipped in
        ``evaluate()`` so it won't fire again.  Call :meth:`delete`
        after confirming delivery to clean up.
        """
        if trigger_id in self._triggers:
            self._fired_once_ids.add(trigger_id)

    def add_on_fire(self, callback: Callable[[TriggerNotification], Awaitable[None]]) -> None:
        """Register an async callback invoked when a trigger fires."""
        self._on_fire_callbacks.append(callback)

    async def evaluate_single(
        self,
        trigger_id: str,
        value: Any,
        previous_value: Any,
        timestamp: datetime,
    ) -> bool:
        """Evaluate a single trigger against *value*.

        Returns ``True`` if the trigger fired.  Does **not** auto-delete
        one-shot triggers — the caller decides whether to delete.

        Used for immediate evaluation at creation time so the response
        can indicate the condition was already satisfied.
        """
        trigger = self._triggers.get(trigger_id)
        if trigger is None:
            return False

        if not _matches(trigger.condition, value, previous_value):
            return False

        now = time.monotonic()
        self._last_fire_times[trigger_id] = now
        notification = TriggerNotification(
            trigger_id=trigger_id,
            field=trigger.condition.field,
            operator=trigger.condition.operator,
            threshold=trigger.condition.value,
            value=value,
            previous_value=previous_value,
            fired_at=timestamp,
            vin=self._vin,
            once=trigger.once,
        )

        logger.info(
            "Trigger %s fired (immediate): %s %s %s (value=%s)",
            trigger_id,
            trigger.condition.field,
            trigger.condition.operator.value,
            trigger.condition.value,
            value,
        )

        if trigger.once:
            self._fired_once_ids.add(trigger_id)

        for callback in self._on_fire_callbacks:
            try:
                await callback(notification)
            except Exception:
                logger.warning("Trigger fire callback failed for %s", trigger_id, exc_info=True)

        return True

    async def evaluate(
        self,
        field: str,
        value: Any,
        previous_value: Any,
        timestamp: datetime,
    ) -> bool:
        """Evaluate all triggers registered for *field*.

        Returns ``True`` if at least one trigger fired for this field/value.

        One-shot triggers are **not** deleted here.  Instead they are
        tracked in ``_fired_once_ids`` and skipped on subsequent
        evaluations.  The push callback (or caller) is responsible for
        calling :meth:`delete` after confirming delivery.

        Called by the bridge after capturing the previous value and
        before updating the telemetry store.
        """
        trigger_ids = self._field_index.get(field)
        if not trigger_ids:
            return False

        fired = False
        now = time.monotonic()
        for tid in list(trigger_ids):
            trigger = self._triggers.get(tid)
            if trigger is None:
                continue

            # Skip one-shot triggers that already fired (pending delivery)
            if tid in self._fired_once_ids:
                continue

            # Cooldown check for persistent triggers
            if not trigger.once:
                last_fire = self._last_fire_times.get(tid)
                if last_fire is not None and (now - last_fire) < trigger.cooldown_seconds:
                    continue

            if not _matches(trigger.condition, value, previous_value):
                continue

            # Fire!
            fired = True
            self._last_fire_times[tid] = now
            notification = TriggerNotification(
                trigger_id=tid,
                field=field,
                operator=trigger.condition.operator,
                threshold=trigger.condition.value,
                value=value,
                previous_value=previous_value,
                fired_at=timestamp,
                vin=self._vin,
                once=trigger.once,
            )

            logger.info(
                "Trigger %s fired: %s %s %s (value=%s prev=%s)",
                tid,
                field,
                trigger.condition.operator.value,
                trigger.condition.value,
                value,
                previous_value,
            )

            # Mark one-shot triggers as fired (pending delivery).
            # Deletion is deferred until the push callback confirms
            # successful WebSocket delivery.
            if trigger.once:
                self._fired_once_ids.add(tid)

            for callback in self._on_fire_callbacks:
                try:
                    await callback(notification)
                except Exception:
                    logger.warning("Trigger fire callback failed for %s", tid, exc_info=True)

        return fired


def _matches(condition: TriggerCondition, value: Any, previous_value: Any) -> bool:
    """Check whether a value satisfies a trigger condition."""
    op = condition.operator

    if op == TriggerOperator.CHANGED:
        return bool(value != previous_value)

    if op == TriggerOperator.EQ:
        return bool(value == condition.value)

    if op == TriggerOperator.NEQ:
        return bool(value != condition.value)

    if op in (TriggerOperator.ENTER, TriggerOperator.LEAVE):
        return _matches_geofence(condition, value, previous_value)

    # Numeric comparisons
    try:
        fval = float(value)
        fthresh = float(condition.value)
    except (TypeError, ValueError):
        logger.debug(
            "Numeric coercion failed for %s %s (value=%r, threshold=%r)",
            condition.field,
            op.value,
            value,
            condition.value,
        )
        return False

    if op == TriggerOperator.LT:
        return fval < fthresh
    if op == TriggerOperator.GT:
        return fval > fthresh
    if op == TriggerOperator.LTE:
        return fval <= fthresh
    if op == TriggerOperator.GTE:
        return fval >= fthresh

    return False


def _matches_geofence(condition: TriggerCondition, value: Any, previous_value: Any) -> bool:
    """Evaluate geofence enter/leave conditions.

    Requires a boundary crossing — being "already inside" doesn't fire
    an ``enter`` trigger.  ``previous_value`` of ``None`` never fires.
    """
    from tescmd.openclaw.filters import haversine

    if previous_value is None:
        return False

    geo = condition.value
    if not isinstance(geo, dict):
        logger.warning("Geofence trigger on %s has non-dict value: %r", condition.field, geo)
        return False

    try:
        center_lat = float(geo["latitude"])
        center_lon = float(geo["longitude"])
        radius = float(geo["radius_m"])
    except (KeyError, TypeError, ValueError):
        logger.warning(
            "Geofence trigger on %s has invalid config (need latitude, longitude, radius_m): %r",
            condition.field,
            geo,
        )
        return False

    try:
        cur_lat = float(value["latitude"])
        cur_lon = float(value["longitude"])
        prev_lat = float(previous_value["latitude"])
        prev_lon = float(previous_value["longitude"])
    except (KeyError, TypeError, ValueError):
        logger.debug(
            "Geofence data missing coordinates for %s (value=%r, prev=%r)",
            condition.field,
            value,
            previous_value,
        )
        return False

    cur_dist = haversine(cur_lat, cur_lon, center_lat, center_lon)
    prev_dist = haversine(prev_lat, prev_lon, center_lat, center_lon)

    if condition.operator == TriggerOperator.ENTER:
        return cur_dist <= radius and prev_dist > radius
    if condition.operator == TriggerOperator.LEAVE:
        return cur_dist > radius and prev_dist <= radius

    return False
