"""CLI commands for media playback control."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._client import execute_command
from tescmd.cli._options import global_options

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext

media_group = click.Group("media", help="Media playback commands")


@media_group.command("play-pause")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def play_pause_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Toggle media playback."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "media_toggle_playback",
            "media.play-pause",
            success_message="Media playback toggled.",
        )
    )


@media_group.command("next-track")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def next_track_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Skip to next track."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "media_next_track",
            "media.next-track",
            success_message="Skipped to next track.",
        )
    )


@media_group.command("prev-track")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def prev_track_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Skip to previous track."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "media_prev_track",
            "media.prev-track",
            success_message="Skipped to previous track.",
        )
    )


@media_group.command("next-fav")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def next_fav_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Skip to next favourite."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "media_next_fav",
            "media.next-fav",
            success_message="Skipped to next favorite.",
        )
    )


@media_group.command("prev-fav")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def prev_fav_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Skip to previous favourite."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "media_prev_fav",
            "media.prev-fav",
            success_message="Skipped to previous favorite.",
        )
    )


@media_group.command("volume-up")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def volume_up_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Increase volume by one step."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "media_volume_up",
            "media.volume-up",
            success_message="Volume increased.",
        )
    )


@media_group.command("volume-down")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@global_options
def volume_down_cmd(app_ctx: AppContext, vin_positional: str | None) -> None:
    """Decrease volume by one step."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "media_volume_down",
            "media.volume-down",
            success_message="Volume decreased.",
        )
    )


@media_group.command("adjust-volume")
@click.argument("vin_positional", required=False, default=None, metavar="VIN")
@click.argument("volume", type=click.IntRange(0, 11))
@global_options
def adjust_volume_cmd(app_ctx: AppContext, vin_positional: str | None, volume: int) -> None:
    """Set volume to VOLUME (0-11)."""
    run_async(
        execute_command(
            app_ctx,
            vin_positional,
            "adjust_volume",
            "media.adjust-volume",
            body={"volume": volume},
            success_message=f"Volume set to {volume}.",
        )
    )
