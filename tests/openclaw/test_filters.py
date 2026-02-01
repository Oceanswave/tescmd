"""Tests for DualGateFilter and haversine distance."""

from __future__ import annotations

from tescmd.openclaw.config import FieldFilter
from tescmd.openclaw.filters import DualGateFilter, haversine


class TestHaversine:
    def test_same_point_is_zero(self) -> None:
        assert haversine(40.0, -74.0, 40.0, -74.0) == 0.0

    def test_known_distance(self) -> None:
        # New York (40.7128, -74.0060) to Los Angeles (34.0522, -118.2437)
        # ~3944 km
        dist = haversine(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3_900_000 < dist < 4_000_000  # meters

    def test_short_distance(self) -> None:
        # Two points ~111m apart (0.001 degrees latitude at equator)
        dist = haversine(0.0, 0.0, 0.001, 0.0)
        assert 100 < dist < 120  # ~111m

    def test_antipodal_points(self) -> None:
        # Opposite sides of Earth: ~20,000 km
        dist = haversine(0.0, 0.0, 0.0, 180.0)
        assert 20_000_000 < dist < 20_100_000


class TestDualGateFilter:
    def _make_filter(self, **fields: tuple[float, float]) -> DualGateFilter:
        """Helper: create filter from field_name → (granularity, throttle_seconds)."""
        filters = {}
        for name, (gran, throttle) in fields.items():
            filters[name] = FieldFilter(granularity=gran, throttle_seconds=throttle)
        return DualGateFilter(filters)

    def test_first_value_always_emits(self) -> None:
        filt = self._make_filter(Soc=(5.0, 10.0))
        assert filt.should_emit("Soc", 72, 0.0) is True

    def test_unknown_field_rejected(self) -> None:
        filt = self._make_filter(Soc=(5.0, 10.0))
        assert filt.should_emit("Unknown", 42, 0.0) is False

    def test_disabled_field_rejected(self) -> None:
        filters = {"Soc": FieldFilter(enabled=False, granularity=0.0, throttle_seconds=0.0)}
        filt = DualGateFilter(filters)
        assert filt.should_emit("Soc", 72, 0.0) is False

    def test_delta_below_threshold_rejected(self) -> None:
        filt = self._make_filter(Soc=(5.0, 0.0))
        assert filt.should_emit("Soc", 72, 0.0) is True
        filt.record_emit("Soc", 72, 0.0)
        # Change of 2, below granularity of 5
        assert filt.should_emit("Soc", 74, 1.0) is False

    def test_delta_at_threshold_emits(self) -> None:
        filt = self._make_filter(Soc=(5.0, 0.0))
        assert filt.should_emit("Soc", 72, 0.0) is True
        filt.record_emit("Soc", 72, 0.0)
        # Change of 5, equal to granularity
        assert filt.should_emit("Soc", 77, 1.0) is True

    def test_delta_above_threshold_emits(self) -> None:
        filt = self._make_filter(Soc=(5.0, 0.0))
        assert filt.should_emit("Soc", 72, 0.0) is True
        filt.record_emit("Soc", 72, 0.0)
        assert filt.should_emit("Soc", 80, 1.0) is True

    def test_throttle_blocks_rapid_emissions(self) -> None:
        filt = self._make_filter(Soc=(0.0, 10.0))
        assert filt.should_emit("Soc", 72, 0.0) is True
        filt.record_emit("Soc", 72, 0.0)
        # Value changed, but throttle (10s) not elapsed
        assert filt.should_emit("Soc", 80, 5.0) is False

    def test_throttle_allows_after_interval(self) -> None:
        filt = self._make_filter(Soc=(0.0, 10.0))
        assert filt.should_emit("Soc", 72, 0.0) is True
        filt.record_emit("Soc", 72, 0.0)
        # Throttle elapsed, value changed
        assert filt.should_emit("Soc", 80, 11.0) is True

    def test_zero_granularity_emits_on_any_change(self) -> None:
        filt = self._make_filter(ChargeState=(0.0, 0.0))
        assert filt.should_emit("ChargeState", "Charging", 0.0) is True
        filt.record_emit("ChargeState", "Charging", 0.0)
        # Same value — should NOT emit
        assert filt.should_emit("ChargeState", "Charging", 1.0) is False
        # Different value — should emit
        assert filt.should_emit("ChargeState", "Complete", 1.0) is True

    def test_location_uses_haversine(self) -> None:
        filt = self._make_filter(Location=(50.0, 0.0))  # 50m granularity
        loc1 = {"latitude": 40.7128, "longitude": -74.0060}
        loc2 = {"latitude": 40.7128, "longitude": -74.0060}  # same
        loc3 = {"latitude": 40.7138, "longitude": -74.0060}  # ~111m away

        assert filt.should_emit("Location", loc1, 0.0) is True
        filt.record_emit("Location", loc1, 0.0)

        # Same location — below 50m threshold
        assert filt.should_emit("Location", loc2, 1.0) is False

        # ~111m away — above 50m threshold
        assert filt.should_emit("Location", loc3, 1.0) is True

    def test_both_gates_must_pass(self) -> None:
        """Delta passes but throttle blocks."""
        filt = self._make_filter(Soc=(5.0, 10.0))
        assert filt.should_emit("Soc", 72, 0.0) is True
        filt.record_emit("Soc", 72, 0.0)
        # Big delta (10) but throttle not elapsed (5s < 10s)
        assert filt.should_emit("Soc", 82, 5.0) is False
        # Throttle elapsed (11s > 10s)
        assert filt.should_emit("Soc", 82, 11.0) is True

    def test_reset_clears_state(self) -> None:
        filt = self._make_filter(Soc=(5.0, 10.0))
        filt.record_emit("Soc", 72, 0.0)
        filt.reset()
        # After reset, first value always emits
        assert filt.should_emit("Soc", 72, 0.0) is True

    def test_non_numeric_value_treated_as_changed(self) -> None:
        filt = self._make_filter(Gear=(1.0, 0.0))
        assert filt.should_emit("Gear", "D", 0.0) is True
        filt.record_emit("Gear", "D", 0.0)
        # Non-numeric delta → infinity → always passes
        assert filt.should_emit("Gear", "R", 1.0) is True
