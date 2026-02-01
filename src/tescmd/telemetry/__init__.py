"""Fleet Telemetry streaming — WebSocket server, decoder, and dashboard."""

from __future__ import annotations

from tescmd.telemetry.decoder import TelemetryDatum, TelemetryDecoder, TelemetryFrame
from tescmd.telemetry.fields import FIELD_NAMES, PRESETS, resolve_fields
from tescmd.telemetry.server import TelemetryServer
from tescmd.telemetry.setup import TelemetrySession, telemetry_session
from tescmd.telemetry.tailscale import TailscaleManager

__all__ = [
    "FIELD_NAMES",
    "PRESETS",
    "TailscaleManager",
    "TelemetryDatum",
    "TelemetryDecoder",
    "TelemetryFrame",
    "TelemetryServer",
    "TelemetrySession",
    "resolve_fields",
    "telemetry_session",
]
