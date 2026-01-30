"""Tests for cache key generation."""

from __future__ import annotations

from tescmd.cache.keys import cache_key


class TestCacheKey:
    def test_no_endpoints_returns_vin_all(self) -> None:
        assert cache_key("VIN123") == "VIN123_all"

    def test_no_endpoints_none_returns_vin_all(self) -> None:
        assert cache_key("VIN123", None) == "VIN123_all"

    def test_empty_endpoints_returns_vin_all(self) -> None:
        assert cache_key("VIN123", []) == "VIN123_all"

    def test_with_endpoints_returns_vin_hash(self) -> None:
        key = cache_key("VIN123", ["charge_state"])
        assert key.startswith("VIN123_")
        assert key != "VIN123_all"
        # Hash portion is 12 hex chars
        assert len(key.split("_", 1)[1]) == 12

    def test_order_independent(self) -> None:
        key_ab = cache_key("VIN", ["charge_state", "drive_state"])
        key_ba = cache_key("VIN", ["drive_state", "charge_state"])
        assert key_ab == key_ba

    def test_different_endpoints_different_keys(self) -> None:
        key_a = cache_key("VIN", ["charge_state"])
        key_b = cache_key("VIN", ["drive_state"])
        assert key_a != key_b

    def test_different_vins_different_keys(self) -> None:
        key_a = cache_key("VIN_A", ["charge_state"])
        key_b = cache_key("VIN_B", ["charge_state"])
        assert key_a != key_b
