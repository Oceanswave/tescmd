"""Tests for ResponseCache."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tescmd.cache.response_cache import ResponseCache


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir: Path) -> ResponseCache:
    return ResponseCache(cache_dir=cache_dir, default_ttl=60, enabled=True)


SAMPLE_DATA = {"charge_state": {"battery_level": 72}}
VIN = "5YJ3E1EA1NF000001"


class TestGetMiss:
    def test_empty_cache_returns_none(self, cache: ResponseCache) -> None:
        assert cache.get(VIN) is None

    def test_unknown_vin_returns_none(self, cache: ResponseCache) -> None:
        cache.put("OTHER_VIN", SAMPLE_DATA)
        assert cache.get(VIN) is None


class TestPutThenGet:
    def test_roundtrip_no_endpoints(self, cache: ResponseCache) -> None:
        cache.put(VIN, SAMPLE_DATA)
        result = cache.get(VIN)
        assert result is not None
        assert result.data == SAMPLE_DATA

    def test_roundtrip_with_endpoints(self, cache: ResponseCache) -> None:
        cache.put(VIN, SAMPLE_DATA, endpoints=["charge_state"])
        result = cache.get(VIN, endpoints=["charge_state"])
        assert result is not None
        assert result.data == SAMPLE_DATA

    def test_different_endpoints_separate_entries(self, cache: ResponseCache) -> None:
        data_a = {"charge_state": {"battery_level": 72}}
        data_b = {"drive_state": {"latitude": 37.7}}
        cache.put(VIN, data_a, endpoints=["charge_state"])
        cache.put(VIN, data_b, endpoints=["drive_state"])
        result_a = cache.get(VIN, endpoints=["charge_state"])
        result_b = cache.get(VIN, endpoints=["drive_state"])
        assert result_a is not None
        assert result_a.data == data_a
        assert result_b is not None
        assert result_b.data == data_b

    def test_cache_result_age_and_ttl(self, cache: ResponseCache) -> None:
        cache.put(VIN, SAMPLE_DATA, ttl=120)
        result = cache.get(VIN)
        assert result is not None
        assert result.age_seconds >= 0
        assert result.ttl_seconds == 120


class TestExpiry:
    def test_expired_entry_returns_none(self, cache_dir: Path) -> None:
        cache = ResponseCache(cache_dir=cache_dir, default_ttl=1, enabled=True)
        # Negative TTL guarantees immediate expiry
        cache.put(VIN, SAMPLE_DATA, ttl=-1)
        assert cache.get(VIN) is None

    def test_custom_ttl_on_put(self, cache: ResponseCache) -> None:
        # TTL=-1 guarantees expiry even if put and get are sub-millisecond apart
        cache.put(VIN, SAMPLE_DATA, ttl=-1)
        assert cache.get(VIN) is None

    def test_expired_file_is_cleaned_up(self, cache: ResponseCache, cache_dir: Path) -> None:
        cache.put(VIN, SAMPLE_DATA, ttl=-1)
        # The file exists but is stale
        files_before = list(cache_dir.glob("*.json"))
        assert len(files_before) == 1
        # Reading it should clean it up
        cache.get(VIN)
        files_after = list(cache_dir.glob("*.json"))
        assert len(files_after) == 0


class TestClear:
    def test_clear_all(self, cache: ResponseCache) -> None:
        cache.put("VIN_A", SAMPLE_DATA)
        cache.put("VIN_B", SAMPLE_DATA)
        removed = cache.clear()
        assert removed == 2
        assert cache.get("VIN_A") is None
        assert cache.get("VIN_B") is None

    def test_clear_by_vin(self, cache: ResponseCache) -> None:
        cache.put("VIN_A", SAMPLE_DATA)
        cache.put("VIN_B", SAMPLE_DATA)
        removed = cache.clear("VIN_A")
        assert removed == 1
        assert cache.get("VIN_A") is None
        result_b = cache.get("VIN_B")
        assert result_b is not None
        assert result_b.data == SAMPLE_DATA

    def test_clear_empty_returns_zero(self, cache: ResponseCache) -> None:
        assert cache.clear() == 0

    def test_clear_nonexistent_dir_returns_zero(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path / "does_not_exist")
        assert cache.clear() == 0


class TestDisabledCache:
    def test_put_is_noop(self, cache_dir: Path) -> None:
        cache = ResponseCache(cache_dir=cache_dir, enabled=False)
        cache.put(VIN, SAMPLE_DATA)
        assert not cache_dir.exists()

    def test_get_always_misses(self, cache_dir: Path) -> None:
        # Put with enabled cache, then read with disabled
        enabled = ResponseCache(cache_dir=cache_dir, enabled=True)
        enabled.put(VIN, SAMPLE_DATA)
        disabled = ResponseCache(cache_dir=cache_dir, enabled=False)
        assert disabled.get(VIN) is None


class TestWakeState:
    def test_wake_state_online(self, cache: ResponseCache) -> None:
        cache.put_wake_state(VIN, "online")
        assert cache.get_wake_state(VIN) is True

    def test_wake_state_asleep(self, cache: ResponseCache) -> None:
        cache.put_wake_state(VIN, "asleep")
        assert cache.get_wake_state(VIN) is False

    def test_wake_state_no_entry(self, cache: ResponseCache) -> None:
        assert cache.get_wake_state(VIN) is False

    def test_wake_state_expires(self, cache_dir: Path) -> None:
        cache = ResponseCache(cache_dir=cache_dir, default_ttl=60, enabled=True)
        cache.put_wake_state(VIN, "online", ttl=-1)
        assert cache.get_wake_state(VIN) is False

    def test_wake_state_disabled(self, cache_dir: Path) -> None:
        cache = ResponseCache(cache_dir=cache_dir, enabled=False)
        cache.put_wake_state(VIN, "online")
        assert cache.get_wake_state(VIN) is False


class TestStatus:
    def test_empty_cache_status(self, cache: ResponseCache) -> None:
        info = cache.status()
        assert info["enabled"] is True
        assert info["total"] == 0
        assert info["fresh"] == 0
        assert info["stale"] == 0
        assert info["disk_bytes"] == 0

    def test_status_counts(self, cache: ResponseCache, cache_dir: Path) -> None:
        # One fresh entry
        cache.put(VIN, SAMPLE_DATA)
        # One stale entry (write directly with expired timestamp)
        stale_path = cache_dir / "stale_entry.json"
        stale_path.write_text(
            json.dumps({"data": {}, "created_at": 0, "expires_at": 0}),
            encoding="utf-8",
        )
        info = cache.status()
        assert info["total"] == 2
        assert info["fresh"] == 1
        assert info["stale"] == 1
        assert info["disk_bytes"] > 0

    def test_status_nonexistent_dir(self, tmp_path: Path) -> None:
        cache = ResponseCache(cache_dir=tmp_path / "nope")
        info = cache.status()
        assert info["total"] == 0


class TestClearByPrefix:
    def test_clears_matching(self, cache: ResponseCache) -> None:
        cache.put_generic("vin_VIN1_aaa", SAMPLE_DATA)
        cache.put_generic("vin_VIN1_bbb", SAMPLE_DATA)
        cache.put_generic("vin_VIN2_ccc", SAMPLE_DATA)
        removed = cache.clear_by_prefix("vin_VIN1_")
        assert removed == 2
        assert cache.get_generic("vin_VIN2_ccc") is not None

    def test_no_match(self, cache: ResponseCache) -> None:
        cache.put_generic("account_global_xyz", SAMPLE_DATA)
        assert cache.clear_by_prefix("partner_") == 0

    def test_empty_dir(self, cache: ResponseCache) -> None:
        assert cache.clear_by_prefix("x_") == 0


class TestCorruptFiles:
    def test_corrupt_json_returns_none(self, cache: ResponseCache, cache_dir: Path) -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        bad_file = cache_dir / f"{VIN}_all.json"
        bad_file.write_text("not valid json!", encoding="utf-8")
        assert cache.get(VIN) is None
