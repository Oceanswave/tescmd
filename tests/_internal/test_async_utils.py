"""Tests for tescmd._internal.async_utils."""

from __future__ import annotations

import pytest

from tescmd._internal.async_utils import run_async


async def _async_add(a: int, b: int) -> int:
    return a + b


async def _async_raise(msg: str) -> None:
    raise ValueError(msg)


class TestRunAsync:
    def test_runs_coroutine_and_returns_result(self) -> None:
        result = run_async(_async_add(2, 3))
        assert result == 5

    def test_propagates_exceptions(self) -> None:
        with pytest.raises(ValueError, match="test error"):
            run_async(_async_raise("test error"))

    def test_returns_none_for_void_coroutine(self) -> None:
        async def void_coro() -> None:
            pass

        result = run_async(void_coro())
        assert result is None
