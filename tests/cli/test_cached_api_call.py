"""Tests for the cached_api_call() helper in cli/_client.py."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

from tescmd.cli._client import TTL_DEFAULT, TTL_FAST, TTL_SLOW, TTL_STATIC, cached_api_call

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------


class _StubRich:
    """Minimal RichOutput stand-in that records info calls."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, msg: str) -> None:
        self.messages.append(msg)


class _StubFormatter:
    """Minimal OutputFormatter stand-in for testing cache metadata behaviour."""

    def __init__(self, fmt: str = "rich") -> None:
        self._format = fmt
        self.rich = _StubRich()
        self._cache_meta: dict[str, Any] | None = None

    @property
    def format(self) -> str:
        return self._format

    def set_cache_meta(self, *, hit: bool, age_seconds: int, ttl_seconds: int) -> None:
        self._cache_meta = {"hit": hit, "age_seconds": age_seconds, "ttl_seconds": ttl_seconds}


@dataclass
class _StubAppCtx:
    """Minimal AppContext stand-in."""

    formatter: _StubFormatter
    no_cache: bool = False
    profile: str = "default"

    # Needed by get_cache() via AppSettings — we patch get_cache instead.


@dataclass
class _StubModel:
    """Fake Pydantic model with model_dump()."""

    value: int

    def model_dump(self) -> dict[str, Any]:
        return {"value": self.value}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def app_ctx() -> _StubAppCtx:
    return _StubAppCtx(formatter=_StubFormatter())


@pytest.fixture
def json_app_ctx() -> _StubAppCtx:
    return _StubAppCtx(formatter=_StubFormatter(fmt="json"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCacheMiss:
    @pytest.mark.asyncio
    async def test_calls_fetch_on_miss(
        self, app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        fetch = AsyncMock(return_value={"items": [1, 2]})
        result = await cached_api_call(
            app_ctx,  # type: ignore[arg-type]
            scope="account",
            identifier="global",
            endpoint="test.endpoint",
            fetch=fetch,
            ttl=TTL_DEFAULT,
        )
        fetch.assert_awaited_once()
        assert result == {"items": [1, 2]}

    @pytest.mark.asyncio
    async def test_stores_result_on_miss(
        self, app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        await cached_api_call(
            app_ctx,  # type: ignore[arg-type]
            scope="vin",
            identifier="VIN123",
            endpoint="vehicle.get",
            fetch=AsyncMock(return_value={"vin": "VIN123"}),
            ttl=TTL_DEFAULT,
        )

        # Verify the cache now has the entry
        from tescmd.cache.keys import generic_cache_key

        key = generic_cache_key("vin", "VIN123", "vehicle.get")
        cached = cache.get_generic(key)
        assert cached is not None
        assert cached.data == {"vin": "VIN123"}

    @pytest.mark.asyncio
    async def test_serialises_pydantic_model(
        self, app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        model = _StubModel(value=42)
        result = await cached_api_call(
            app_ctx,  # type: ignore[arg-type]
            scope="account",
            identifier="global",
            endpoint="test.model",
            fetch=AsyncMock(return_value=model),
            ttl=TTL_STATIC,
        )
        # Returns the original model on miss
        assert result is model

        # Cache stores the dict form
        from tescmd.cache.keys import generic_cache_key

        key = generic_cache_key("account", "global", "test.model")
        cached = cache.get_generic(key)
        assert cached is not None
        assert cached.data == {"value": 42}

    @pytest.mark.asyncio
    async def test_serialises_list_of_models(
        self, app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        models = [_StubModel(value=1), _StubModel(value=2)]
        result = await cached_api_call(
            app_ctx,  # type: ignore[arg-type]
            scope="account",
            identifier="global",
            endpoint="test.list",
            fetch=AsyncMock(return_value=models),
        )
        assert result is models

        from tescmd.cache.keys import generic_cache_key

        key = generic_cache_key("account", "global", "test.list")
        cached = cache.get_generic(key)
        assert cached is not None
        assert cached.data == [{"value": 1}, {"value": 2}]

    @pytest.mark.asyncio
    async def test_wraps_scalar_result(
        self, app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        result = await cached_api_call(
            app_ctx,  # type: ignore[arg-type]
            scope="vin",
            identifier="VIN",
            endpoint="vehicle.mobile-access",
            fetch=AsyncMock(return_value=True),
        )
        assert result is True

        from tescmd.cache.keys import generic_cache_key

        key = generic_cache_key("vin", "VIN", "vehicle.mobile-access")
        cached = cache.get_generic(key)
        assert cached is not None
        assert cached.data == {"_value": True}


class TestCacheHit:
    @pytest.mark.asyncio
    async def test_returns_cached_dict(
        self, app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.keys import generic_cache_key
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        key = generic_cache_key("account", "global", "vehicle.list")
        cache.put_generic(key, [{"vin": "VIN1"}], ttl=300)

        fetch = AsyncMock()
        result = await cached_api_call(
            app_ctx,  # type: ignore[arg-type]
            scope="account",
            identifier="global",
            endpoint="vehicle.list",
            fetch=fetch,
            ttl=300,
        )
        # Returns cached data, fetch NOT called
        fetch.assert_not_awaited()
        assert result == [{"vin": "VIN1"}]

    @pytest.mark.asyncio
    async def test_emits_rich_info_on_hit(
        self, app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.keys import generic_cache_key
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        key = generic_cache_key("vin", "VIN", "vehicle.get")
        cache.put_generic(key, {"vin": "VIN"}, ttl=60)

        await cached_api_call(
            app_ctx,  # type: ignore[arg-type]
            scope="vin",
            identifier="VIN",
            endpoint="vehicle.get",
            fetch=AsyncMock(),
        )
        # Should have emitted a "cached" info message
        assert any("cached" in m.lower() for m in app_ctx.formatter.rich.messages)

    @pytest.mark.asyncio
    async def test_sets_cache_meta_in_json_mode(
        self, json_app_ctx: _StubAppCtx, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.keys import generic_cache_key
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: cache)

        key = generic_cache_key("account", "global", "user.me")
        cache.put_generic(key, {"email": "test@example.com"}, ttl=3600)

        await cached_api_call(
            json_app_ctx,  # type: ignore[arg-type]
            scope="account",
            identifier="global",
            endpoint="user.me",
            fetch=AsyncMock(),
            ttl=3600,
        )
        meta = json_app_ctx.formatter._cache_meta
        assert meta is not None
        assert meta["hit"] is True


class TestFreshFlag:
    @pytest.mark.asyncio
    async def test_no_cache_bypasses(
        self, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tescmd.cache.keys import generic_cache_key
        from tescmd.cache.response_cache import ResponseCache
        from tescmd.cli import _client

        ctx = _StubAppCtx(formatter=_StubFormatter(), no_cache=True)

        # Pre-populate a real enabled cache on disk
        enabled_cache = ResponseCache(cache_dir=cache_dir, enabled=True)
        key = generic_cache_key("account", "global", "vehicle.list")
        enabled_cache.put_generic(key, [{"old": True}], ttl=300)

        # When no_cache=True, get_cache() returns a *disabled* cache — simulate that
        disabled_cache = ResponseCache(cache_dir=cache_dir, enabled=False)
        monkeypatch.setattr(_client, "get_cache", lambda _ctx: disabled_cache)

        fetch = AsyncMock(return_value=[{"fresh": True}])
        result = await cached_api_call(
            ctx,  # type: ignore[arg-type]
            scope="account",
            identifier="global",
            endpoint="vehicle.list",
            fetch=fetch,
            ttl=300,
        )
        # With disabled cache, fetch is always called even though data is on disk
        fetch.assert_awaited_once()
        assert result == [{"fresh": True}]


class TestTTLConstants:
    def test_tier_ordering(self) -> None:
        assert TTL_FAST < TTL_DEFAULT < TTL_SLOW < TTL_STATIC

    def test_values(self) -> None:
        assert TTL_STATIC == 3600
        assert TTL_SLOW == 300
        assert TTL_DEFAULT == 60
        assert TTL_FAST == 30
