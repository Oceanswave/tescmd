"""Tests for the wake confirmation prompt in auto_wake()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tescmd.api.errors import VehicleAsleepError
from tescmd.cli._client import auto_wake
from tescmd.output.formatter import OutputFormatter


def _make_formatter(fmt: str = "rich") -> OutputFormatter:
    return OutputFormatter(force_format=fmt)


def _make_vehicle_api() -> MagicMock:
    api = MagicMock()
    api.wake = AsyncMock()
    return api


@pytest.mark.asyncio
class TestWakeConfirmation:
    async def test_no_prompt_when_vehicle_online(self) -> None:
        """If the operation succeeds, no prompt or wake is needed."""
        formatter = _make_formatter()
        api = _make_vehicle_api()
        operation = AsyncMock(return_value="result")

        result = await auto_wake(formatter, api, "VIN", operation)
        assert result == "result"
        api.wake.assert_not_called()

    async def test_prompts_user_tty_and_wakes_on_confirm(self) -> None:
        """In TTY mode, user is prompted and can choose 'w' to wake."""
        formatter = _make_formatter("rich")
        api = _make_vehicle_api()
        api.wake.return_value = MagicMock(state="online")

        operation = AsyncMock(side_effect=[VehicleAsleepError("asleep", 408), "result"])

        with (
            patch("tescmd.cli._client.sys") as mock_sys,
            patch("tescmd.cli._client.click.prompt", return_value="w"),
            patch("tescmd.cli._client._wake_and_wait", new_callable=AsyncMock),
        ):
            mock_sys.stdin.isatty.return_value = True
            result = await auto_wake(formatter, api, "VIN", operation)

        assert result == "result"

    async def test_cancels_on_decline(self) -> None:
        """In TTY mode, user can choose 'c' to cancel."""
        formatter = _make_formatter("rich")
        api = _make_vehicle_api()
        operation = AsyncMock(side_effect=VehicleAsleepError("asleep", 408))

        with (
            patch("tescmd.cli._client.sys") as mock_sys,
            patch("tescmd.cli._client.click.prompt", return_value="c"),
            pytest.raises(VehicleAsleepError, match="Wake cancelled"),
        ):
            mock_sys.stdin.isatty.return_value = True
            await auto_wake(formatter, api, "VIN", operation)

    async def test_retry_succeeds_when_vehicle_wakes_via_app(self) -> None:
        """Pressing 'r' retries the operation; succeeds if vehicle is now online."""
        formatter = _make_formatter("rich")
        api = _make_vehicle_api()
        # First call: asleep (triggers prompt). Retry: succeeds.
        operation = AsyncMock(side_effect=[VehicleAsleepError("asleep", 408), "result"])

        with (
            patch("tescmd.cli._client.sys") as mock_sys,
            patch("tescmd.cli._client.click.prompt", return_value="r"),
        ):
            mock_sys.stdin.isatty.return_value = True
            result = await auto_wake(formatter, api, "VIN", operation)

        assert result == "result"
        api.wake.assert_not_called()  # No billable wake sent

    async def test_retry_loops_when_still_asleep(self) -> None:
        """Pressing 'r' twice when still asleep re-prompts, then 'w' wakes."""
        formatter = _make_formatter("rich")
        api = _make_vehicle_api()
        api.wake.return_value = MagicMock(state="online")
        # First call: asleep. Retry 1: still asleep. Retry 2: still asleep. Wake+retry: succeeds.
        operation = AsyncMock(
            side_effect=[
                VehicleAsleepError("asleep", 408),  # initial attempt
                VehicleAsleepError("asleep", 408),  # retry 1
                VehicleAsleepError("asleep", 408),  # retry 2
                "result",  # after API wake
            ]
        )

        with (
            patch("tescmd.cli._client.sys") as mock_sys,
            patch("tescmd.cli._client.click.prompt", side_effect=["r", "r", "w"]),
            patch("tescmd.cli._client._wake_and_wait", new_callable=AsyncMock),
        ):
            mock_sys.stdin.isatty.return_value = True
            result = await auto_wake(formatter, api, "VIN", operation)

        assert result == "result"

    async def test_retry_then_cancel(self) -> None:
        """Pressing 'r' then 'c' retries once, then cancels."""
        formatter = _make_formatter("rich")
        api = _make_vehicle_api()
        operation = AsyncMock(side_effect=VehicleAsleepError("asleep", 408))

        with (
            patch("tescmd.cli._client.sys") as mock_sys,
            patch("tescmd.cli._client.click.prompt", side_effect=["r", "c"]),
            pytest.raises(VehicleAsleepError, match="Wake cancelled"),
        ):
            mock_sys.stdin.isatty.return_value = True
            await auto_wake(formatter, api, "VIN", operation)

    async def test_skips_prompt_with_auto_flag(self) -> None:
        """When auto=True (--wake flag), skip prompt and wake immediately."""
        formatter = _make_formatter("rich")
        api = _make_vehicle_api()
        api.wake.return_value = MagicMock(state="online")

        operation = AsyncMock(side_effect=[VehicleAsleepError("asleep", 408), "result"])

        with patch("tescmd.cli._client._wake_and_wait", new_callable=AsyncMock):
            result = await auto_wake(
                formatter,
                api,
                "VIN",
                operation,
                auto=True,
            )

        assert result == "result"

    async def test_json_mode_raises_without_prompt(self) -> None:
        """In JSON mode without --wake, raise immediately with guidance."""
        formatter = _make_formatter("json")
        api = _make_vehicle_api()
        operation = AsyncMock(side_effect=VehicleAsleepError("asleep", 408))

        with pytest.raises(VehicleAsleepError, match="--wake"):
            await auto_wake(formatter, api, "VIN", operation)

    async def test_json_mode_with_auto_wakes(self) -> None:
        """In JSON mode with auto=True, wake without prompt."""
        formatter = _make_formatter("json")
        api = _make_vehicle_api()
        api.wake.return_value = MagicMock(state="online")

        operation = AsyncMock(side_effect=[VehicleAsleepError("asleep", 408), "result"])

        with patch("tescmd.cli._client._wake_and_wait", new_callable=AsyncMock):
            result = await auto_wake(
                formatter,
                api,
                "VIN",
                operation,
                auto=True,
            )

        assert result == "result"
