"""Tests for generic cache key generation and generic cache operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tescmd.cache.keys import generic_cache_key
from tescmd.cache.response_cache import ResponseCache

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# generic_cache_key()
# ---------------------------------------------------------------------------


class TestGenericCacheKey:
    def test_basic_format(self) -> None:
        key = generic_cache_key("account", "global", "vehicle.list")
        assert key.startswith("account_global_")
        # Hash portion is 12 hex chars
        parts = key.split("_", 2)
        assert len(parts) == 3
        assert len(parts[2]) == 12

    def test_deterministic(self) -> None:
        a = generic_cache_key("vin", "VIN123", "vehicle.get")
        b = generic_cache_key("vin", "VIN123", "vehicle.get")
        assert a == b

    def test_different_scopes_different_keys(self) -> None:
        a = generic_cache_key("vin", "VIN123", "some.endpoint")
        b = generic_cache_key("site", "VIN123", "some.endpoint")
        assert a != b

    def test_different_identifiers_different_keys(self) -> None:
        a = generic_cache_key("vin", "VIN_A", "vehicle.get")
        b = generic_cache_key("vin", "VIN_B", "vehicle.get")
        assert a != b

    def test_different_endpoints_different_keys(self) -> None:
        a = generic_cache_key("vin", "VIN123", "vehicle.get")
        b = generic_cache_key("vin", "VIN123", "vehicle.specs")
        assert a != b

    def test_params_change_key(self) -> None:
        a = generic_cache_key("account", "global", "billing.history")
        b = generic_cache_key("account", "global", "billing.history", {"vin": "VIN123"})
        assert a != b

    def test_params_order_independent(self) -> None:
        a = generic_cache_key("account", "global", "billing.history", {"a": "1", "b": "2"})
        b = generic_cache_key("account", "global", "billing.history", {"b": "2", "a": "1"})
        assert a == b

    def test_none_params_same_as_no_params(self) -> None:
        a = generic_cache_key("account", "global", "vehicle.list", None)
        b = generic_cache_key("account", "global", "vehicle.list")
        assert a == b

    def test_empty_params_same_as_no_params(self) -> None:
        a = generic_cache_key("account", "global", "vehicle.list", {})
        b = generic_cache_key("account", "global", "vehicle.list")
        assert a == b


# ---------------------------------------------------------------------------
# ResponseCache generic methods
# ---------------------------------------------------------------------------


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir: Path) -> ResponseCache:
    return ResponseCache(cache_dir=cache_dir, default_ttl=60, enabled=True)


SAMPLE = {"items": [1, 2, 3]}


class TestGetGenericPutGeneric:
    def test_roundtrip(self, cache: ResponseCache) -> None:
        cache.put_generic("account_global_abc123", SAMPLE)
        result = cache.get_generic("account_global_abc123")
        assert result is not None
        assert result.data == SAMPLE

    def test_miss_returns_none(self, cache: ResponseCache) -> None:
        assert cache.get_generic("nonexistent_key") is None

    def test_custom_ttl(self, cache: ResponseCache) -> None:
        cache.put_generic("key", SAMPLE, ttl=300)
        result = cache.get_generic("key")
        assert result is not None
        assert result.ttl_seconds == 300

    def test_expired_returns_none(self, cache: ResponseCache) -> None:
        cache.put_generic("key", SAMPLE, ttl=-1)
        assert cache.get_generic("key") is None

    def test_disabled_cache_get_returns_none(self, cache_dir: Path) -> None:
        disabled = ResponseCache(cache_dir=cache_dir, enabled=False)
        assert disabled.get_generic("any_key") is None

    def test_disabled_cache_put_is_noop(self, cache_dir: Path) -> None:
        disabled = ResponseCache(cache_dir=cache_dir, enabled=False)
        disabled.put_generic("any_key", SAMPLE)
        assert not cache_dir.exists()

    def test_different_keys_are_isolated(self, cache: ResponseCache) -> None:
        data_a = {"x": 1}
        data_b = {"x": 2}
        cache.put_generic("key_a", data_a)
        cache.put_generic("key_b", data_b)
        assert cache.get_generic("key_a") is not None
        assert cache.get_generic("key_a").data == data_a  # type: ignore[union-attr]
        assert cache.get_generic("key_b") is not None
        assert cache.get_generic("key_b").data == data_b  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# clear_by_prefix()
# ---------------------------------------------------------------------------


class TestClearByPrefix:
    def test_clears_matching_entries(self, cache: ResponseCache) -> None:
        cache.put_generic("site_123_aaa", SAMPLE)
        cache.put_generic("site_123_bbb", SAMPLE)
        cache.put_generic("site_456_ccc", SAMPLE)
        removed = cache.clear_by_prefix("site_123_")
        assert removed == 2
        assert cache.get_generic("site_123_aaa") is None
        assert cache.get_generic("site_123_bbb") is None
        assert cache.get_generic("site_456_ccc") is not None

    def test_no_matches_returns_zero(self, cache: ResponseCache) -> None:
        cache.put_generic("account_global_xyz", SAMPLE)
        assert cache.clear_by_prefix("site_") == 0

    def test_empty_cache_returns_zero(self, cache: ResponseCache) -> None:
        assert cache.clear_by_prefix("anything_") == 0

    def test_nonexistent_dir_returns_zero(self, tmp_path: Path) -> None:
        c = ResponseCache(cache_dir=tmp_path / "nope")
        assert c.clear_by_prefix("x_") == 0

    def test_scoped_clearing(self, cache: ResponseCache) -> None:
        """Verify account, partner, vin, site scopes are independently clearable."""
        cache.put_generic("account_global_a1", SAMPLE)
        cache.put_generic("partner_global_b2", SAMPLE)
        cache.put_generic("vin_VIN1_c3", SAMPLE)
        cache.put_generic("site_99_d4", SAMPLE)

        cache.clear_by_prefix("account_")
        assert cache.get_generic("account_global_a1") is None
        # Others untouched
        assert cache.get_generic("partner_global_b2") is not None
        assert cache.get_generic("vin_VIN1_c3") is not None
        assert cache.get_generic("site_99_d4") is not None
