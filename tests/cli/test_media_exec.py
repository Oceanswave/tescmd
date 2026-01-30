"""Execution tests for the media CLI commands.

Each test mocks the Fleet API via ``httpx_mock`` (pytest-httpx), invokes the
Click CLI through ``CliRunner``, and asserts on the JSON output envelope.

All media commands use ``execute_command()`` and POST to
``/api/1/vehicles/{vin}/command/{method}``.

Simple commands (play-pause, next-track, etc.) use the env VIN and no extra args.
``adjust-volume`` takes a positional VIN and VOLUME argument.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"

COMMAND_OK: dict[str, Any] = {"response": {"result": True, "reason": ""}}


def _request_body(httpx_mock: HTTPXMock, idx: int = 0) -> dict[str, Any]:
    """Parse the JSON body of the idx-th captured request."""
    return json.loads(httpx_mock.get_requests()[idx].content)  # type: ignore[no-any-return]


# =============================================================================
# Simple media commands (no extra parameters, use env VIN)
# =============================================================================


class TestMediaPlayPause:
    """Tests for ``tescmd media play-pause``."""

    def test_play_pause(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_toggle_playback",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "play-pause"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.play-pause"
        assert parsed["data"]["response"]["result"] is True

    def test_play_pause_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_toggle_playback",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "play-pause"],
            catch_exceptions=False,
        )
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "media_toggle_playback" in str(requests[0].url)
        assert requests[0].method == "POST"


class TestMediaNextTrack:
    """Tests for ``tescmd media next-track``."""

    def test_next_track(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_next_track",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "next-track"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.next-track"
        assert parsed["data"]["response"]["result"] is True


class TestMediaPrevTrack:
    """Tests for ``tescmd media prev-track``."""

    def test_prev_track(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_prev_track",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "prev-track"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.prev-track"
        assert parsed["data"]["response"]["result"] is True


class TestMediaNextFav:
    """Tests for ``tescmd media next-fav``."""

    def test_next_fav(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_next_fav",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "next-fav"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.next-fav"
        assert parsed["data"]["response"]["result"] is True


class TestMediaPrevFav:
    """Tests for ``tescmd media prev-fav``."""

    def test_prev_fav(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_prev_fav",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "prev-fav"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.prev-fav"
        assert parsed["data"]["response"]["result"] is True


class TestMediaVolumeUp:
    """Tests for ``tescmd media volume-up``."""

    def test_volume_up(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_volume_up",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "volume-up"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.volume-up"
        assert parsed["data"]["response"]["result"] is True


class TestMediaVolumeDown:
    """Tests for ``tescmd media volume-down``."""

    def test_volume_down(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_volume_down",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "volume-down"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.volume-down"
        assert parsed["data"]["response"]["result"] is True


# =============================================================================
# Parameterised — adjust-volume
# =============================================================================


class TestMediaAdjustVolume:
    """Tests for ``tescmd media adjust-volume VIN VOLUME``."""

    def test_adjust_volume(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/adjust_volume",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "adjust-volume", VIN, "5"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.adjust-volume"
        assert parsed["data"]["response"]["result"] is True

    def test_adjust_volume_sends_correct_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """adjust-volume sends the volume value in the request body."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/adjust_volume",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "adjust-volume", VIN, "8"],
            catch_exceptions=False,
        )
        body = _request_body(httpx_mock)
        assert body["volume"] == 8

    def test_adjust_volume_min(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """adjust-volume accepts minimum value 0."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/adjust_volume",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "adjust-volume", VIN, "0"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.adjust-volume"

    def test_adjust_volume_max(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        """adjust-volume accepts maximum value 11."""
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/adjust_volume",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "adjust-volume", VIN, "11"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "media.adjust-volume"

    def test_adjust_volume_rejects_out_of_range(self) -> None:
        """adjust-volume rejects values outside 0-11."""
        runner = CliRunner()
        result = runner.invoke(cli, ["media", "adjust-volume", VIN, "12"])
        assert result.exit_code != 0

    def test_adjust_volume_rejects_negative(self) -> None:
        """adjust-volume rejects negative values."""
        runner = CliRunner()
        result = runner.invoke(cli, ["media", "adjust-volume", VIN, "-1"])
        assert result.exit_code != 0


# =============================================================================
# Output envelope structure
# =============================================================================


class TestMediaOutputEnvelope:
    """Verify the JSON envelope structure shared by all media commands."""

    def test_envelope_has_timestamp(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_toggle_playback",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "play-pause"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert "timestamp" in parsed

    def test_envelope_data_contains_result(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/command/media_next_track",
            method="POST",
            json=COMMAND_OK,
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "--wake", "media", "next-track"],
            catch_exceptions=False,
        )
        parsed = json.loads(result.output)
        assert parsed["data"]["response"]["result"] is True
        assert parsed["data"]["response"]["reason"] == ""
