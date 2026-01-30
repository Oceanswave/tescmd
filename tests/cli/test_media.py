"""Tests for the media CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from tescmd.cli.main import cli


class TestMediaHelp:
    def test_media_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "--help"])
        assert result.exit_code == 0
        assert "play-pause" in result.output
        assert "next-track" in result.output
        assert "prev-track" in result.output
        assert "next-fav" in result.output
        assert "prev-fav" in result.output
        assert "volume-up" in result.output
        assert "volume-down" in result.output
        assert "adjust-volume" in result.output

    def test_media_in_root_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert "media" in result.output


class TestMediaPlayPause:
    def test_play_pause_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "play-pause", "--help"])
        assert result.exit_code == 0
        assert "Toggle media playback" in result.output

    def test_play_pause_accepts_vin_positional(self) -> None:
        result = CliRunner().invoke(cli, ["media", "play-pause", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output


class TestMediaNextTrack:
    def test_next_track_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "next-track", "--help"])
        assert result.exit_code == 0
        assert "next track" in result.output.lower()


class TestMediaPrevTrack:
    def test_prev_track_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "prev-track", "--help"])
        assert result.exit_code == 0
        assert "previous track" in result.output.lower()


class TestMediaNextFav:
    def test_next_fav_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "next-fav", "--help"])
        assert result.exit_code == 0
        assert "favourite" in result.output.lower() or "fav" in result.output.lower()


class TestMediaPrevFav:
    def test_prev_fav_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "prev-fav", "--help"])
        assert result.exit_code == 0
        assert "favourite" in result.output.lower() or "fav" in result.output.lower()


class TestMediaVolumeUp:
    def test_volume_up_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "volume-up", "--help"])
        assert result.exit_code == 0
        assert "volume" in result.output.lower()


class TestMediaVolumeDown:
    def test_volume_down_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "volume-down", "--help"])
        assert result.exit_code == 0
        assert "volume" in result.output.lower()


class TestMediaAdjustVolume:
    def test_adjust_volume_help(self) -> None:
        result = CliRunner().invoke(cli, ["media", "adjust-volume", "--help"])
        assert result.exit_code == 0
        assert "VOLUME" in result.output
        assert "0" in result.output
        assert "11" in result.output

    def test_adjust_volume_accepts_vin_positional(self) -> None:
        result = CliRunner().invoke(cli, ["media", "adjust-volume", "--help"])
        assert result.exit_code == 0
        assert "VIN" in result.output
