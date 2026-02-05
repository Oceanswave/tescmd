"""Tests for TriggerManager — evaluation engine, cooldown, delivery."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from tescmd.triggers.manager import TriggerLimitError, TriggerManager, _matches
from tescmd.triggers.models import (
    TriggerCondition,
    TriggerDefinition,
    TriggerNotification,
    TriggerOperator,
)

TS = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)


def _cond(field: str, op: TriggerOperator, value: Any = None) -> TriggerCondition:
    return TriggerCondition(field=field, operator=op, value=value)


def _trig(
    field: str,
    op: TriggerOperator,
    value: Any = None,
    *,
    once: bool = False,
    cooldown: float = 60.0,
) -> TriggerDefinition:
    return TriggerDefinition(
        condition=_cond(field, op, value),
        once=once,
        cooldown_seconds=cooldown,
    )


class TestCreate:
    def test_returns_trigger_with_id(self) -> None:
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("Soc", TriggerOperator.LT, 20))
        assert len(t.id) == 12
        assert mgr.list_all() == [t]

    def test_enforces_max_limit(self) -> None:
        mgr = TriggerManager(vin="V")
        for _ in range(100):
            mgr.create(_trig("Soc", TriggerOperator.LT, 20))
        with pytest.raises(TriggerLimitError):
            mgr.create(_trig("Soc", TriggerOperator.LT, 20))

    def test_rejects_missing_value_for_non_changed(self) -> None:
        from pydantic import ValidationError

        mgr = TriggerManager(vin="V")
        with pytest.raises(ValidationError, match="requires a 'value'"):
            mgr.create(_trig("Soc", TriggerOperator.LT, None))

    def test_allows_none_value_for_changed(self) -> None:
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("Locked", TriggerOperator.CHANGED, None))
        assert t.condition.value is None


class TestDelete:
    def test_returns_true_on_existing(self) -> None:
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("Soc", TriggerOperator.LT, 20))
        assert mgr.delete(t.id) is True
        assert mgr.list_all() == []

    def test_returns_false_on_missing(self) -> None:
        mgr = TriggerManager(vin="V")
        assert mgr.delete("nonexistent") is False

    def test_removes_from_field_index(self) -> None:
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("Soc", TriggerOperator.LT, 20))
        mgr.delete(t.id)
        assert "Soc" not in mgr._field_index


class TestListAll:
    def test_empty(self) -> None:
        mgr = TriggerManager(vin="V")
        assert mgr.list_all() == []

    def test_returns_all(self) -> None:
        mgr = TriggerManager(vin="V")
        t1 = mgr.create(_trig("Soc", TriggerOperator.LT, 20))
        t2 = mgr.create(_trig("InsideTemp", TriggerOperator.GT, 35))
        assert set(t.id for t in mgr.list_all()) == {t1.id, t2.id}


class TestEvaluate:
    @pytest.mark.asyncio
    async def test_lt_fires(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))
        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].value == 15.0

    @pytest.mark.asyncio
    async def test_lt_does_not_fire_above(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))
        await mgr.evaluate("Soc", 25.0, 30.0, TS)
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_gt_fires(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("VehicleSpeed", TriggerOperator.GT, 80, cooldown=0))
        await mgr.evaluate("VehicleSpeed", 85.0, 70.0, TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_lte_fires_at_boundary(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("OutsideTemp", TriggerOperator.LTE, 32, cooldown=0))
        await mgr.evaluate("OutsideTemp", 32.0, 35.0, TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_gte_fires_at_boundary(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("InsideTemp", TriggerOperator.GTE, 35, cooldown=0))
        await mgr.evaluate("InsideTemp", 35.0, 30.0, TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_eq_fires(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("ChargeState", TriggerOperator.EQ, "Charging", cooldown=0))
        await mgr.evaluate("ChargeState", "Charging", "Stopped", TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_eq_does_not_fire(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("ChargeState", TriggerOperator.EQ, "Charging", cooldown=0))
        await mgr.evaluate("ChargeState", "Stopped", "Charging", TS)
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_neq_fires(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Gear", TriggerOperator.NEQ, "P", cooldown=0))
        await mgr.evaluate("Gear", "D", "P", TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_changed_fires(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Locked", TriggerOperator.CHANGED, cooldown=0))
        await mgr.evaluate("Locked", False, True, TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_changed_does_not_fire_same_value(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Locked", TriggerOperator.CHANGED, cooldown=0))
        await mgr.evaluate("Locked", True, True, TS)
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_non_numeric_lt_returns_false(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))
        await mgr.evaluate("Soc", "not-a-number", 25.0, TS)
        assert mgr.drain_pending() == []


class TestCooldown:
    @pytest.mark.asyncio
    async def test_persistent_respects_cooldown(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=60.0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        assert len(mgr.drain_pending()) == 1

        # Second fire within cooldown — should NOT fire
        await mgr.evaluate("Soc", 10.0, 15.0, TS)
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_fires_after_cooldown_expires(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0.01))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        assert len(mgr.drain_pending()) == 1

        # Simulate time passing past cooldown

        time.sleep(0.02)

        await mgr.evaluate("Soc", 10.0, 15.0, TS)
        assert len(mgr.drain_pending()) == 1


class TestOnce:
    @pytest.mark.asyncio
    async def test_one_shot_stays_until_delivery(self) -> None:
        """One-shot triggers remain registered after firing (pending delivery)."""
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, once=True, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        assert len(mgr.drain_pending()) == 1
        # Trigger still exists — waiting for push callback to confirm delivery
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_one_shot_fires_only_once(self) -> None:
        """One-shot trigger fires once, then is skipped on subsequent evaluations."""
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, once=True, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        await mgr.evaluate("Soc", 10.0, 15.0, TS)
        pending = mgr.drain_pending()
        # Only one notification — second evaluate skipped the fired trigger
        assert len(pending) == 1

    @pytest.mark.asyncio
    async def test_one_shot_deleted_after_explicit_delete(self) -> None:
        """One-shot trigger is removed when delete() is called (simulating delivery)."""
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("Soc", TriggerOperator.LT, 20, once=True, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        assert len(mgr.list_all()) == 1

        mgr.delete(t.id)
        assert mgr.list_all() == []

    @pytest.mark.asyncio
    async def test_one_shot_notification_carries_once_flag(self) -> None:
        """Notification from a one-shot trigger has once=True."""
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, once=True, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].once is True

    @pytest.mark.asyncio
    async def test_persistent_notification_once_is_false(self) -> None:
        """Notification from a persistent trigger has once=False."""
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, once=False, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].once is False


class TestDelivery:
    @pytest.mark.asyncio
    async def test_callback_invoked(self) -> None:
        mgr = TriggerManager(vin="V")
        cb = AsyncMock()
        mgr.add_on_fire(cb)
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        cb.assert_awaited_once()
        notification = cb.call_args[0][0]
        assert isinstance(notification, TriggerNotification)
        assert notification.value == 15.0

    @pytest.mark.asyncio
    async def test_pending_populated(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].trigger_id

    @pytest.mark.asyncio
    async def test_drain_clears(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        mgr.drain_pending()
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_callback_failure_does_not_block(self) -> None:
        mgr = TriggerManager(vin="V")
        bad_cb = AsyncMock(side_effect=RuntimeError("boom"))
        good_cb = AsyncMock()
        mgr.add_on_fire(bad_cb)
        mgr.add_on_fire(good_cb)
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        # Both callbacks called; failure in first doesn't block second
        bad_cb.assert_awaited_once()
        good_cb.assert_awaited_once()
        # Notification still in pending despite callback failure
        assert len(mgr.drain_pending()) == 1


class TestPendingOverflow:
    @pytest.mark.asyncio
    async def test_oldest_notifications_dropped_on_overflow(self) -> None:
        from tescmd.triggers.manager import MAX_PENDING

        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.CHANGED, None, cooldown=0))

        # Fill beyond MAX_PENDING
        for i in range(MAX_PENDING + 10):
            await mgr.evaluate("Soc", float(i), float(i - 1) if i > 0 else None, TS)

        pending = mgr.drain_pending()
        assert len(pending) == MAX_PENDING
        # Oldest should have been dropped — first pending value should be 10.0
        assert pending[0].value == 10.0
        assert pending[-1].value == float(MAX_PENDING + 9)


class TestFieldIndex:
    @pytest.mark.asyncio
    async def test_only_matching_field_evaluated(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))
        mgr.create(_trig("InsideTemp", TriggerOperator.GT, 35, cooldown=0))

        await mgr.evaluate("Soc", 15.0, 25.0, TS)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].field == "Soc"

    @pytest.mark.asyncio
    async def test_multiple_triggers_same_field(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))
        mgr.create(_trig("Soc", TriggerOperator.LT, 10, cooldown=0))

        await mgr.evaluate("Soc", 5.0, 25.0, TS)
        pending = mgr.drain_pending()
        # Both triggers should fire (value 5 is < 20 and < 10)
        assert len(pending) == 2

    @pytest.mark.asyncio
    async def test_unregistered_field_is_noop(self) -> None:
        mgr = TriggerManager(vin="V")
        mgr.create(_trig("Soc", TriggerOperator.LT, 20, cooldown=0))

        await mgr.evaluate("UnknownField", 42, None, TS)
        assert mgr.drain_pending() == []


class TestGeofence:
    """Test enter/leave geofence triggers."""

    # San Francisco: 37.7749, -122.4194
    # ~1km away: 37.7839, -122.4194

    @pytest.mark.asyncio
    async def test_enter_fires_on_crossing_inward(self) -> None:
        mgr = TriggerManager(vin="V")
        geo = {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 500}
        mgr.create(_trig("Location", TriggerOperator.ENTER, geo, cooldown=0))

        prev = {"latitude": 37.79, "longitude": -122.4194}  # ~1.7km away
        curr = {"latitude": 37.7749, "longitude": -122.4194}  # at center

        await mgr.evaluate("Location", curr, prev, TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_leave_fires_on_crossing_outward(self) -> None:
        mgr = TriggerManager(vin="V")
        geo = {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 500}
        mgr.create(_trig("Location", TriggerOperator.LEAVE, geo, cooldown=0))

        prev = {"latitude": 37.7749, "longitude": -122.4194}  # at center
        curr = {"latitude": 37.79, "longitude": -122.4194}  # ~1.7km away

        await mgr.evaluate("Location", curr, prev, TS)
        assert len(mgr.drain_pending()) == 1

    @pytest.mark.asyncio
    async def test_no_fire_without_previous(self) -> None:
        mgr = TriggerManager(vin="V")
        geo = {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 500}
        mgr.create(_trig("Location", TriggerOperator.ENTER, geo, cooldown=0))

        curr = {"latitude": 37.7749, "longitude": -122.4194}

        await mgr.evaluate("Location", curr, None, TS)
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_no_fire_when_already_inside(self) -> None:
        mgr = TriggerManager(vin="V")
        geo = {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 500}
        mgr.create(_trig("Location", TriggerOperator.ENTER, geo, cooldown=0))

        # Both inside — no boundary crossing
        prev = {"latitude": 37.7750, "longitude": -122.4194}
        curr = {"latitude": 37.7749, "longitude": -122.4194}

        await mgr.evaluate("Location", curr, prev, TS)
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_no_fire_when_already_outside(self) -> None:
        mgr = TriggerManager(vin="V")
        geo = {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 500}
        mgr.create(_trig("Location", TriggerOperator.LEAVE, geo, cooldown=0))

        # Both outside — no boundary crossing
        prev = {"latitude": 37.80, "longitude": -122.4194}  # ~2.8km away
        curr = {"latitude": 37.79, "longitude": -122.4194}  # ~1.7km away

        await mgr.evaluate("Location", curr, prev, TS)
        assert mgr.drain_pending() == []

    @pytest.mark.asyncio
    async def test_haversine_accuracy(self) -> None:
        """Verify haversine at known distance (SF to Oakland ~13km)."""
        from tescmd.openclaw.filters import haversine

        sf_lat, sf_lon = 37.7749, -122.4194
        oak_lat, oak_lon = 37.8044, -122.2712

        dist = haversine(sf_lat, sf_lon, oak_lat, oak_lon)
        # Should be ~13.5km
        assert 13_000 < dist < 14_000


class TestMatches:
    """Direct tests for the _matches() helper."""

    def test_changed_different(self) -> None:
        c = _cond("f", TriggerOperator.CHANGED)
        assert _matches(c, "a", "b") is True

    def test_changed_same(self) -> None:
        c = _cond("f", TriggerOperator.CHANGED)
        assert _matches(c, "a", "a") is False

    def test_eq_match(self) -> None:
        c = _cond("f", TriggerOperator.EQ, "x")
        assert _matches(c, "x", None) is True

    def test_eq_no_match(self) -> None:
        c = _cond("f", TriggerOperator.EQ, "x")
        assert _matches(c, "y", None) is False

    def test_neq_match(self) -> None:
        c = _cond("f", TriggerOperator.NEQ, "x")
        assert _matches(c, "y", None) is True

    def test_lt_numeric(self) -> None:
        c = _cond("f", TriggerOperator.LT, 20)
        assert _matches(c, 15, None) is True
        assert _matches(c, 25, None) is False

    def test_gt_numeric(self) -> None:
        c = _cond("f", TriggerOperator.GT, 80)
        assert _matches(c, 85, None) is True
        assert _matches(c, 75, None) is False

    def test_lte_boundary(self) -> None:
        c = _cond("f", TriggerOperator.LTE, 20)
        assert _matches(c, 20, None) is True
        assert _matches(c, 21, None) is False

    def test_gte_boundary(self) -> None:
        c = _cond("f", TriggerOperator.GTE, 80)
        assert _matches(c, 80, None) is True
        assert _matches(c, 79, None) is False

    def test_non_numeric_returns_false(self) -> None:
        c = _cond("f", TriggerOperator.LT, 20)
        assert _matches(c, "abc", None) is False

    def test_string_numeric_coercion(self) -> None:
        c = _cond("f", TriggerOperator.GT, "80")
        assert _matches(c, "85", None) is True


class TestEvaluateSingle:
    """Tests for evaluate_single — one-trigger evaluation without side-effects."""

    @pytest.mark.asyncio
    async def test_returns_true_on_match(self) -> None:
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("BatteryLevel", TriggerOperator.LT, 20))

        fired = await mgr.evaluate_single(t.id, 15.0, None, TS)

        assert fired is True
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].value == 15.0

    @pytest.mark.asyncio
    async def test_returns_false_on_no_match(self) -> None:
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("BatteryLevel", TriggerOperator.LT, 20))

        fired = await mgr.evaluate_single(t.id, 50.0, None, TS)

        assert fired is False
        assert len(mgr.drain_pending()) == 0

    @pytest.mark.asyncio
    async def test_returns_false_for_missing_id(self) -> None:
        mgr = TriggerManager(vin="V")

        fired = await mgr.evaluate_single("nonexistent", 15.0, None, TS)

        assert fired is False

    @pytest.mark.asyncio
    async def test_does_not_auto_delete(self) -> None:
        """evaluate_single does NOT auto-delete one-shot triggers."""
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("BatteryLevel", TriggerOperator.LT, 20, once=True))

        fired = await mgr.evaluate_single(t.id, 15.0, None, TS)

        assert fired is True
        # Trigger should still exist — caller handles deletion
        assert len(mgr.list_all()) == 1

    @pytest.mark.asyncio
    async def test_calls_fire_callbacks(self) -> None:
        mgr = TriggerManager(vin="V")
        t = mgr.create(_trig("BatteryLevel", TriggerOperator.LT, 20))

        cb = AsyncMock()
        mgr.add_on_fire(cb)

        await mgr.evaluate_single(t.id, 15.0, None, TS)

        cb.assert_awaited_once()
        assert cb.call_args[0][0].field == "BatteryLevel"


class TestQueueNotification:
    """Tests for queue_notification and vin property."""

    def test_queue_notification(self) -> None:
        mgr = TriggerManager(vin="V")
        n = TriggerNotification(
            trigger_id="t1", field="f", operator=TriggerOperator.LT,
            threshold=20, value=15, vin="V",
        )
        mgr.queue_notification(n)
        pending = mgr.drain_pending()
        assert len(pending) == 1
        assert pending[0].trigger_id == "t1"

    def test_vin_property(self) -> None:
        mgr = TriggerManager(vin="MYVIN")
        assert mgr.vin == "MYVIN"
