"""Full-screen Textual TUI dashboard for telemetry + server monitoring.

Multi-panel dashboard with categorized vehicle widgets, keybindings for
vehicle commands, and a help/info modal screen.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, RichLog, Static

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from textual.screen import Screen

    from tescmd.output.rich_output import DisplayUnits
    from tescmd.telemetry.decoder import TelemetryFrame
    from tescmd.triggers.manager import TriggerManager

logger = logging.getLogger(__name__)


def _make_cli_runner() -> Any:
    """Create a CliRunner with stderr separation.

    Click 8.2 removed the ``mix_stderr`` parameter (stderr is always
    separate).  Click 8.1 defaults to ``mix_stderr=True``, so we pass
    ``False`` when supported.  Routed through ``Any`` to avoid a
    version-dependent ``type: ignore`` that fails strict mypy on one
    version or the other.
    """
    from click.testing import CliRunner as _Runner

    _ctor: Any = _Runner
    try:
        return _ctor(mix_stderr=False)
    except TypeError:
        return _Runner()


# ---------------------------------------------------------------------------
# Panel field mapping — declarative schema for the dashboard layout
# ---------------------------------------------------------------------------

PANEL_FIELDS: dict[str, tuple[str, list[str]]] = {
    "battery": (
        "Battery & Charging",
        [
            "Soc",
            "BatteryLevel",
            "EstBatteryRange",
            "IdealBatteryRange",
            "RatedRange",
            "PackVoltage",
            "PackCurrent",
            "ChargeState",
            "DetailedChargeState",
            "ChargeLimitSoc",
            "TimeToFullCharge",
            "ACChargingPower",
            "DCChargingPower",
            "ChargerVoltage",
            "ChargeAmps",
            "ChargePortDoorOpen",
            "ChargePortLatch",
            "FastChargerPresent",
            "FastChargerType",
            "ChargingCableType",
            "BatteryHeaterOn",
            "EnergyRemaining",
            "ChargeCurrentRequest",
            "ChargeCurrentRequestMax",
            "ChargeRateMilePerHour",
            "EstimatedHoursToChargeTermination",
        ],
    ),
    "climate": (
        "Climate",
        [
            "InsideTemp",
            "OutsideTemp",
            "HvacLeftTemperatureRequest",
            "HvacRightTemperatureRequest",
            "HvacPower",
            "HvacFanStatus",
            "HvacFanSpeed",
            "HvacACEnabled",
            "HvacAutoMode",
            "DefrostMode",
            "DefrostForPreconditioning",
            "SeatHeaterLeft",
            "SeatHeaterRight",
            "SeatHeaterRearLeft",
            "SeatHeaterRearCenter",
            "SeatHeaterRearRight",
            "HvacSteeringWheelHeatLevel",
            "HvacSteeringWheelHeatAuto",
            "AutoSeatClimateLeft",
            "AutoSeatClimateRight",
            "ClimateSeatCoolingFrontLeft",
            "ClimateSeatCoolingFrontRight",
            "SeatVentEnabled",
            "RearDisplayHvacEnabled",
            "RearDefrostEnabled",
            "ClimateKeeperMode",
            "CabinOverheatProtectionMode",
            "CabinOverheatProtectionTemperatureLimit",
            "PreconditioningEnabled",
        ],
    ),
    "driving": (
        "Driving",
        [
            "VehicleSpeed",
            "Location",
            "Gear",
            "GpsHeading",
            "Odometer",
            "CruiseSetSpeed",
            "CruiseFollowDistance",
            "CurrentLimitMph",
            "SpeedLimitMode",
            "SpeedLimitWarning",
            "LateralAcceleration",
            "LongitudinalAcceleration",
            "PedalPosition",
            "BrakePedalPos",
            "LaneDepartureAvoidance",
            "ForwardCollisionWarning",
        ],
    ),
    "nav": (
        "Navigation",
        [
            "MilesToArrival",
            "MinutesToArrival",
            "RouteTrafficMinutesDelay",
            "DestinationName",
            "DestinationLocation",
            "OriginLocation",
            "RouteLine",
            "RouteLastUpdated",
            "ExpectedEnergyPercentAtTripArrival",
            "HomelinkNearby",
            "HomelinkDeviceCount",
            "LocatedAtHome",
            "LocatedAtWork",
            "LocatedAtFavorite",
        ],
    ),
    "security": (
        "Security",
        [
            "Locked",
            "SentryMode",
            "ValetModeEnabled",
            "DoorState",
            "FdWindow",
            "FpWindow",
            "RdWindow",
            "RpWindow",
            "DriverSeatOccupied",
            "DriverSeatBelt",
            "PassengerSeatBelt",
            "CenterDisplay",
            "RemoteStartEnabled",
            "GuestModeEnabled",
            "GuestModeMobileAccessState",
            "PinToDriveEnabled",
        ],
    ),
    "media": (
        "Media",
        [
            "MediaPlaybackStatus",
            "MediaPlaybackSource",
            "MediaNowPlayingTitle",
            "MediaNowPlayingArtist",
            "MediaNowPlayingAlbum",
            "MediaNowPlayingStation",
            "MediaNowPlayingDuration",
            "MediaNowPlayingElapsed",
            "MediaAudioVolume",
            "MediaAudioVolumeMax",
            "MediaAudioVolumeIncrement",
        ],
    ),
    "tires": (
        "Tires",
        [
            "TpmsPressureFl",
            "TpmsPressureFr",
            "TpmsPressureRl",
            "TpmsPressureRr",
            "TpmsLastSeenPressureTimeFl",
            "TpmsLastSeenPressureTimeFr",
            "TpmsLastSeenPressureTimeRl",
            "TpmsLastSeenPressureTimeRr",
            "TpmsHardWarnings",
            "TpmsSoftWarnings",
        ],
    ),
    "diagnostics": (
        "Diagnostics & Vehicle",
        [
            "ModuleTempMax",
            "ModuleTempMin",
            "BrickVoltageMax",
            "BrickVoltageMin",
            "NumBrickVoltageMax",
            "NumBrickVoltageMin",
            "NumModuleTempMax",
            "NumModuleTempMin",
            "BMSState",
            "DriveRail",
            "NotEnoughPowerToHeat",
            "DCDCEnable",
            "IsolationResistance",
            "Hvil",
            "Version",
            "SoftwareUpdateVersion",
            "SoftwareUpdateDownloadPercentComplete",
            "SoftwareUpdateInstallationPercentComplete",
            "CarType",
            "WheelType",
            "ServiceMode",
        ],
    ),
}

# Pre-compute field → panel_id lookup for O(1) routing.
_FIELD_TO_PANEL: dict[str, str] = {}
for _pid, (_title, _fields) in PANEL_FIELDS.items():
    for _f in _fields:
        _FIELD_TO_PANEL[_f] = _pid


# ---------------------------------------------------------------------------
# Activity sidebar — logging handler that funnels into an asyncio queue
# ---------------------------------------------------------------------------

# Logger-name prefix -> (short label, Rich color).
SOURCE_MAP: dict[str, tuple[str, str]] = {
    "tescmd.tui.commands": ("CMD", "cyan"),
    "tescmd.mcp.server": ("MCP", "magenta"),
    "tescmd.cli.serve": ("HTTP", "blue"),
    "tescmd.openclaw.gateway": ("CLAW", "green"),
    "tescmd.openclaw.bridge": ("CLAW", "green"),
    "tescmd.telemetry.server": ("TELEM", "yellow"),
    "tescmd.telemetry.cache_sink": ("CACHE", "dim"),
    "tescmd.api.client": ("API", "blue"),
    "tescmd.api.signed_command": ("SIGN", "bright_red"),
    "tescmd.protocol.session": ("PROTO", "bright_blue"),
}


class ActivityLogHandler(logging.Handler):
    """Logging handler that enqueues messages for the TUI activity sidebar."""

    def __init__(self, queue: asyncio.Queue[tuple[str, str, str]]) -> None:
        super().__init__()
        self._queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        source = "LOG"
        color = "white"
        for prefix, (label, clr) in SOURCE_MAP.items():
            if record.name.startswith(prefix):
                source = label
                color = clr
                break
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait((source, color, self.format(record)))


def _mask_vin(vin: str) -> str:
    """Mask VIN for display — last 4 characters replaced with XXXX."""
    if len(vin) >= 4:
        return vin[:-4] + "XXXX"
    return vin


# ---------------------------------------------------------------------------
# Help / Info modal screen
# ---------------------------------------------------------------------------

_HELP_TEXT = (
    "KEYBINDINGS\n"
    "\n"
    "General\n"
    "  q          Quit\n"
    "  ?          Toggle this help screen\n"
    "\n"
    "Security\n"
    "  l          Lock doors\n"
    "  u          Unlock doors\n"
    "  h          Honk horn\n"
    "  f          Flash lights\n"
    "  s/S        Sentry on / off\n"
    "  r          Remote start\n"
    "  v/V        Valet on / off\n"
    "  g/G        Guest mode on / off\n"
    "\n"
    "Charging\n"
    "  c/C        Start / stop charging\n"
    "  p/P        Port open / close\n"
    "  m          Charge limit max\n"
    "  n          Charge limit standard\n"
    "\n"
    "Climate\n"
    "  a/A        Climate on / off\n"
    "  w/W        Wheel heater on / off\n"
    "\n"
    "Trunk & Windows\n"
    "  t          Trunk open/close\n"
    "  T          Frunk open\n"
    "\n"
    "Media\n"
    "  space      Play / Pause\n"
    "  \\]         Next track\n"
    "  \\[         Previous track\n"
    "  =          Volume up\n"
    "  -          Volume down\n"
    "\n"
    "Vehicle\n"
    "  ctrl+w     Wake vehicle\n"
    "\n"
    "Additional commands (no keybinding):\n"
    "  Auto-secure, Valet reset, PIN to drive,\n"
    "  Boombox, Precondition, Overheat protect,\n"
    "  Bioweapon defense, Auto wheel heater,\n"
    "  Defrost, Trunk close, Window vent/close,\n"
    "  Sunroof, Tonneau, Next/prev fav,\n"
    "  Supercharger nav, HomeLink, Software cancel,\n"
    "  Low power mode, Accessory power,\n"
    "  Charge schedule on/off\n"
)


class HelpScreen(ModalScreen[None]):
    """Modal help screen showing all keybindings and server info."""

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-container {
        width: 64;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #help-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #help-body {
        height: auto;
    }
    #help-extra {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, log_path: str = "", server_info: str = "") -> None:
        super().__init__()
        self._log_path = log_path
        self._server_info = server_info

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-container"):
            yield Static("tescmd Dashboard Help", id="help-title")
            yield Static(_HELP_TEXT, id="help-body")
            extra_parts: list[str] = []
            if self._log_path:
                extra_parts.append(f"Log: {self._log_path}")
            if self._server_info:
                extra_parts.append(self._server_info)
            if extra_parts:
                yield Static("\n".join(extra_parts), id="help-extra")


# ---------------------------------------------------------------------------
# Main TUI application
# ---------------------------------------------------------------------------


class TelemetryTUI(App[None]):
    """Full-screen dashboard for tescmd telemetry and server monitoring.

    **Frame ingestion** works via a bounded :class:`asyncio.Queue`:

    - ``push_frame()`` enqueues frames from the telemetry fanout.
    - A background worker pulls frames and updates internal state.
    - A periodic timer (1 s) refreshes visible widgets from state.

    This decouples the high-frequency telemetry stream from the render
    cycle so the UI stays responsive.
    """

    TITLE = "tescmd"

    CSS = """
    #main-area {
        height: 1fr;
    }
    #panel-grid {
        width: 3fr;
        height: 1fr;
        grid-size: 2;
        grid-gutter: 0;
    }
    #sidebar {
        width: 1fr;
        min-width: 30;
        height: 1fr;
    }
    #triggers-table {
        height: auto;
        min-height: 5;
        max-height: 12;
        border: solid #e67e22;
        padding: 0;
    }
    #activity-log {
        height: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    .telemetry-panel {
        height: 1fr;
        border: solid $primary;
        padding: 0;
    }
    .telemetry-panel DataTable {
        height: 1fr;
    }
    #battery-panel { border: solid #f1c40f; }
    #climate-panel { border: solid #3498db; }
    #driving-panel { border: solid #2ecc71; }
    #security-panel { border: solid #e74c3c; }
    #tires-panel { border: solid #9b59b6; }
    #diagnostics-panel { border: solid #95a5a6; }
    #media-panel { border: solid #e67e22; }
    #nav-panel { border: solid #1abc9c; }
    #server-bar {
        height: auto;
        background: $panel;
        padding: 0 1;
        display: none;
    }
    #command-status {
        height: auto;
        background: $panel;
        padding: 0 1;
        display: none;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        # -- General --
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        # -- Security (shown in footer) --
        Binding("l", "cmd_lock", "Lock"),
        Binding("u", "cmd_unlock", "Unlock"),
        Binding("h", "cmd_honk", "Honk"),
        Binding("f", "cmd_flash", "Flash"),
        Binding("s", "cmd_sentry_on", "Sentry On"),
        Binding("S", "cmd_sentry_off", "Sentry Off", key_display="shift+s"),
        # -- Charging (shown in footer) --
        Binding("c", "cmd_charge_start", "Charge"),
        Binding("C", "cmd_charge_stop", "Charge Stop", key_display="shift+c"),
        # -- Security (hidden — accessible via palette / help) --
        Binding("r", "cmd_remote_start", "Remote Start", show=False),
        Binding("v", "cmd_valet_on", "Valet On", show=False),
        Binding("V", "cmd_valet_off", "Valet Off", key_display="shift+v", show=False),
        Binding("g", "cmd_guest_on", "Guest On", show=False),
        Binding("G", "cmd_guest_off", "Guest Off", key_display="shift+g", show=False),
        # -- Charging (hidden) --
        Binding("p", "cmd_port_open", "Port Open", show=False),
        Binding("P", "cmd_port_close", "Port Close", key_display="shift+p", show=False),
        Binding("m", "cmd_charge_max", "Charge Max", show=False),
        Binding("n", "cmd_charge_std", "Charge Std", show=False),
        # -- Climate (hidden) --
        Binding("a", "cmd_climate_on", "Climate On", show=False),
        Binding("A", "cmd_climate_off", "Climate Off", key_display="shift+a", show=False),
        Binding("w", "cmd_wheel_heater_on", "Wheel Heat On", show=False),
        Binding("W", "cmd_wheel_heater_off", "Wheel Heat Off", key_display="shift+w", show=False),
        # -- Trunk (hidden) --
        Binding("t", "cmd_trunk", "Trunk", show=False),
        Binding("T", "cmd_frunk", "Frunk", key_display="shift+t", show=False),
        # -- Media --
        Binding("space", "cmd_play_pause", "Play/Pause", show=False),
        Binding("right_square_bracket", "cmd_next_track", "]Next", show=False),
        Binding("left_square_bracket", "cmd_prev_track", "[Prev", show=False),
        Binding("equals_sign", "cmd_vol_up", "Vol+", show=False),
        Binding("minus", "cmd_vol_down", "Vol-", show=False),
        # -- Vehicle --
        Binding("ctrl+w", "cmd_wake", "Wake", show=False),
    ]

    def __init__(
        self,
        units: DisplayUnits | None = None,
        *,
        vin: str = "",
        telemetry_port: int | None = None,
    ) -> None:
        super().__init__()
        self._units = units
        self._vin = vin
        self._telemetry_port = telemetry_port

        # Telemetry state.
        self._state: dict[str, Any] = {}
        self._timestamps: dict[str, datetime] = {}
        self._frame_count: int = 0
        self._started_at: datetime = datetime.now(tz=UTC)
        self._connected: bool = False

        # Server info (set by callers after resources are ready).
        self._mcp_url: str = ""
        self._tunnel_url: str = ""
        self._sink_count: int = 0
        self._openclaw_status: str = ""
        self._cache_stats: str = ""
        self._log_path: str = ""

        # Bounded queue for frame ingestion.
        self._queue: asyncio.Queue[TelemetryFrame] = asyncio.Queue(maxsize=100)

        # Track which field names already have rows per panel.
        self._panel_table_fields: dict[str, set[str]] = {pid: set() for pid in PANEL_FIELDS}

        # Shutdown event — signalled when the TUI exits (e.g. user presses q).
        # serve.py can await this to know when to tear down the MCP server.
        self.shutdown_event: asyncio.Event = asyncio.Event()

        # Activity sidebar.
        self._activity_queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue(maxsize=500)
        self._activity_handler: ActivityLogHandler | None = None
        self._last_frame_summary_count: int = 0
        self._ui_tick: int = 0
        self._original_propagate: dict[str, bool] = {}
        self._saved_root_handlers: list[logging.Handler] = []
        self._activity_file_handler: logging.FileHandler | None = None
        self._activity_log_path: str = ""

        # Trigger manager reference (set by serve.py after construction).
        self._trigger_manager: TriggerManager | None = None
        self._trigger_table_keys: set[str] = set()

        # Debug logger for command attempts — always writes to a file.
        self._cmd_logger = logging.getLogger("tescmd.tui.commands")
        self._cmd_log_handler: logging.FileHandler | None = None

    # -- Compose layout -------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-area"):
            with Grid(id="panel-grid"):
                for panel_id in PANEL_FIELDS:
                    with Vertical(id=f"{panel_id}-panel", classes="telemetry-panel"):
                        yield DataTable(
                            id=f"{panel_id}-table", cursor_type="none", zebra_stripes=True
                        )
            with Vertical(id="sidebar"):
                yield DataTable(id="triggers-table", cursor_type="none")
                yield RichLog(id="activity-log", wrap=True, markup=True)
        yield Static(id="server-bar")
        yield Static(id="command-status")
        yield Footer()

    def on_mount(self) -> None:
        """Set up DataTable columns per panel and start background processing."""
        for panel_id, (title, _fields) in PANEL_FIELDS.items():
            panel = self.query_one(f"#{panel_id}-panel", Vertical)
            panel.border_title = title

            table = self.query_one(f"#{panel_id}-table", DataTable)
            table.add_column("Field", key="field", width=24)
            table.add_column("Value", key="value", width=24)

        # Triggers table.
        triggers_table = self.query_one("#triggers-table", DataTable)
        triggers_table.border_title = "Triggers"
        triggers_table.add_column("Field", key="field", width=14)
        triggers_table.add_column("Condition", key="condition", width=10)
        triggers_table.add_column("Type", key="type", width=6)

        # Activity sidebar title.
        activity_log = self.query_one("#activity-log", RichLog)
        activity_log.border_title = "Activity"

        # Set up debug command log file.
        self._setup_command_log()

        # Attach activity handler to all monitored loggers.
        self._setup_activity_handler()

        # Periodic UI refresh.
        self.set_interval(1.0, self._update_ui)

        # Background worker to drain the frame queue.
        self.run_worker(self._process_queue, exclusive=True, thread=False)  # type: ignore[arg-type]

        # Background worker to drain the activity queue into the RichLog.
        self.run_worker(self._process_activity_queue, exclusive=False, thread=False)  # type: ignore[arg-type]

    def _setup_command_log(self) -> None:
        """Set up a file-based debug logger for command attempts."""
        from pathlib import Path

        # Place log next to the CSV log if set, otherwise default config dir.
        if self._log_path:
            log_dir = Path(self._log_path).parent
        else:
            log_dir = Path("~/.config/tescmd").expanduser()
            log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "tui-commands.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        fmt = "%(asctime)s  %(levelname)-5s  %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
        self._cmd_logger.addHandler(handler)
        self._cmd_logger.setLevel(logging.DEBUG)
        self._cmd_log_handler = handler
        self._cmd_log_path = str(log_file)
        self._cmd_logger.info("TUI started — VIN=%s", self._vin or "(none)")

    # -- Activity sidebar -------------------------------------------------------

    def _setup_activity_handler(self) -> None:
        """Attach a logging handler to all monitored loggers.

        Disables propagation so records go ONLY to the activity sidebar,
        not to the console (which would corrupt the Textual TUI).
        """
        handler = ActivityLogHandler(self._activity_queue)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._activity_handler = handler

        # File handler — mirrors activity to a log file for post-mortem.
        from pathlib import Path

        if self._log_path:
            log_dir = Path(self._log_path).parent
        else:
            log_dir = Path("~/.config/tescmd").expanduser()
            log_dir.mkdir(parents=True, exist_ok=True)
        activity_file = log_dir / "tui-activity.log"
        file_handler = logging.FileHandler(activity_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-5s  [%(name)s]  %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        self._activity_file_handler = file_handler
        self._activity_log_path = str(activity_file)

        # Attach handlers and disable console propagation for monitored loggers.
        for logger_name in SOURCE_MAP:
            log = logging.getLogger(logger_name)
            log.addHandler(handler)
            log.addHandler(file_handler)
            log.setLevel(min(log.level or logging.DEBUG, logging.DEBUG))
            self._original_propagate[logger_name] = log.propagate
            log.propagate = False

        # Suppress noisy library loggers that would corrupt the terminal.
        for name in (
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "httpx",
            "httpcore",
            "websockets",
            "mcp",
        ):
            log = logging.getLogger(name)
            self._original_propagate[name] = log.propagate
            log.propagate = False

        # Remove root logger's stream handlers to prevent ANY stray
        # console output while the TUI owns the terminal.
        self._saved_root_handlers = logging.root.handlers[:]
        logging.root.handlers = [
            h
            for h in logging.root.handlers
            if not isinstance(h, logging.StreamHandler) or isinstance(h, logging.FileHandler)
        ]

    async def _process_activity_queue(self) -> None:
        """Background worker: drain activity queue into the RichLog widget."""
        while True:
            try:
                source, color, message = await asyncio.wait_for(
                    self._activity_queue.get(), timeout=0.5
                )
            except TimeoutError:
                continue

            ts = datetime.now(tz=UTC).strftime("%H:%M:%S")
            rich_log = self.query_one("#activity-log", RichLog)
            rich_log.write(f"[{color}]{ts} {source}[/{color}] {message}")

    def _maybe_log_frame_summary(self) -> None:
        """Every 5 UI ticks, log a frame summary if new frames arrived."""
        self._ui_tick += 1
        if self._ui_tick % 5 != 0:
            return
        current = self._frame_count
        delta = current - self._last_frame_summary_count
        if delta > 0:
            self._last_frame_summary_count = current
            ts = datetime.now(tz=UTC).strftime("%H:%M:%S")
            with contextlib.suppress(Exception):
                rich_log = self.query_one("#activity-log", RichLog)
                rich_log.write(f"[yellow]{ts} TELEM[/yellow] +{delta} frames ({current} total)")

    def _cleanup_activity_handler(self) -> None:
        """Remove activity handler and restore console logging."""
        handler = self._activity_handler
        if handler is None:
            return
        for logger_name in SOURCE_MAP:
            log = logging.getLogger(logger_name)
            log.removeHandler(handler)
            if self._activity_file_handler is not None:
                log.removeHandler(self._activity_file_handler)

        if self._activity_file_handler is not None:
            self._activity_file_handler.close()
            self._activity_file_handler = None

        # Restore propagation settings.
        for logger_name, propagate in self._original_propagate.items():
            logging.getLogger(logger_name).propagate = propagate
        self._original_propagate.clear()

        # Restore root logger handlers.
        logging.root.handlers = self._saved_root_handlers
        self._saved_root_handlers = []

        self._activity_handler = None

    # -- Frame ingestion (called from fanout) ---------------------------------

    async def push_frame(self, frame: TelemetryFrame) -> None:
        """Enqueue a telemetry frame for processing.

        Matches the :class:`~tescmd.telemetry.fanout.FrameFanout` callback
        signature.  If the queue is full, the frame is silently dropped
        to prevent memory growth.
        """
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(frame)

    async def _process_queue(self) -> None:
        """Background worker: drain the queue and update state + widgets."""
        while True:
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                continue

            self._frame_count += 1
            self._connected = True
            if frame.vin:
                self._vin = frame.vin

            for datum in frame.data:
                self._state[datum.field_name] = datum.value
                self._timestamps[datum.field_name] = frame.created_at
                self._update_panel_cell(datum.field_name, datum.value)

    # -- Server info setters (called from serve.py) ---------------------------

    def set_mcp_url(self, url: str) -> None:
        self._mcp_url = url

    def set_tunnel_url(self, url: str) -> None:
        self._tunnel_url = url

    def set_sink_count(self, n: int) -> None:
        self._sink_count = n

    def set_openclaw_status(self, connected: bool, send_count: int, event_count: int) -> None:
        status = "Connected" if connected else "Disconnected"
        self._openclaw_status = f"{status} (sent={send_count}, events={event_count})"

    def set_cache_stats(self, frames: int, fields: int, pending: int) -> None:
        self._cache_stats = f"{frames} frames, {fields} fields, {pending} pending"

    def set_log_path(self, path: Path | str) -> None:
        self._log_path = str(path)

    def set_trigger_manager(self, mgr: TriggerManager) -> None:
        self._trigger_manager = mgr

    # -- UI update (runs every 1 second) --------------------------------------

    def _update_ui(self) -> None:
        """Refresh all visible widgets from current state."""
        self._update_header()
        self._update_server_info()
        self._update_triggers()
        self._maybe_log_frame_summary()

    def _update_header(self) -> None:
        now = datetime.now(tz=UTC)
        uptime = now - self._started_at
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Title: VIN + connection status.
        vin_display = _mask_vin(self._vin) if self._vin else "(waiting)"
        status = "Connected" if self._connected else "Waiting"
        self.title = f"tescmd  {vin_display}  [{status}]"

        # Subtitle: frames + uptime (renders right-aligned beside clock).
        self.sub_title = (
            f"Frames: {self._frame_count:,}  Up: {hours:02d}:{minutes:02d}:{seconds:02d}"
        )

    def _update_panel_cell(self, field_name: str, value: Any) -> None:
        """Update a single field's cell in the appropriate panel DataTable."""
        panel_id = _FIELD_TO_PANEL.get(field_name, "diagnostics")
        display_value = _format_value(field_name, value, self._units)
        tracked = self._panel_table_fields[panel_id]

        table = self.query_one(f"#{panel_id}-table", DataTable)
        if field_name in tracked:
            table.update_cell(field_name, "value", display_value)
        else:
            table.add_row(field_name, display_value, key=field_name)
            tracked.add(field_name)

    def _update_server_info(self) -> None:
        parts: list[str] = []
        # Tunnel first — it's the public entry point.
        if self._tunnel_url:
            parts.append(f"Tunnel: {self._tunnel_url}")
        # MCP as relative path (port/path) when tunnel is present.
        if self._mcp_url:
            parts.append(f"MCP: {_relative_path(self._mcp_url, self._tunnel_url)}")
        # Telemetry WS port.
        if self._telemetry_port is not None:
            parts.append(f"WS: :{self._telemetry_port}")
        if self._sink_count:
            parts.append(f"Sinks: {self._sink_count}")
        if self._cache_stats:
            parts.append(f"Cache: {self._cache_stats}")
        if self._openclaw_status:
            parts.append(f"OpenClaw: {self._openclaw_status}")

        info_widget = self.query_one("#server-bar", Static)
        if parts:
            info_widget.update("  |  ".join(parts))
            info_widget.display = True
        else:
            info_widget.update("")
            info_widget.display = False

    def _update_triggers(self) -> None:
        """Refresh the triggers DataTable from the trigger manager."""
        if self._trigger_manager is None:
            return

        table = self.query_one("#triggers-table", DataTable)
        triggers = self._trigger_manager.list_all()
        current_ids = {t.id for t in triggers}

        # Remove rows for deleted triggers.
        removed = self._trigger_table_keys - current_ids
        for tid in removed:
            table.remove_row(tid)
        self._trigger_table_keys -= removed

        # Add or update rows.
        for t in triggers:
            cond = t.condition
            op = cond.operator.value
            if op == "changed":
                condition_text = "changed"
            elif op in ("enter", "leave"):
                condition_text = f"{op} geofence"
            else:
                symbols = {
                    "lt": "<",
                    "gt": ">",
                    "lte": "\u2264",
                    "gte": "\u2265",
                    "eq": "=",
                    "neq": "\u2260",
                }
                condition_text = f"{symbols.get(op, op)} {cond.value}"
            fire_type = "once" if t.once else "persist"

            if t.id in self._trigger_table_keys:
                table.update_cell(t.id, "condition", condition_text)
                table.update_cell(t.id, "type", fire_type)
            else:
                table.add_row(cond.field, condition_text, fire_type, key=t.id)
                self._trigger_table_keys.add(t.id)

    # -- Command execution (keybinding actions) --------------------------------

    def _show_command_status(self, text: str) -> None:
        widget = self.query_one("#command-status", Static)
        widget.update(text)
        widget.display = True

    def _hide_command_status(self) -> None:
        widget = self.query_one("#command-status", Static)
        widget.display = False

    def _run_command(self, cli_args: list[str], description: str) -> None:
        """Run a CLI command in a background thread worker."""
        self._show_command_status(f"Sending: {description}...")
        self._cmd_logger.info("%s  args=%s", description, cli_args)

        async def _invoke() -> None:
            from tescmd.cli.main import cli

            # Suppress httpx/httpcore logging during invocation — their INFO
            # lines write directly to the terminal and corrupt the TUI display.
            _noisy_loggers = ("httpx", "httpcore")
            saved_levels = {n: logging.getLogger(n).level for n in _noisy_loggers}
            for n in _noisy_loggers:
                logging.getLogger(n).setLevel(logging.WARNING)

            runner = _make_cli_runner()
            env = os.environ.copy()
            if self._vin:
                env["TESLA_VIN"] = self._vin
            try:
                result = runner.invoke(cli, ["--format", "json", "--wake", *cli_args], env=env)
            finally:
                for n in _noisy_loggers:
                    logging.getLogger(n).setLevel(saved_levels[n])

            if result.exit_code == 0:
                self._cmd_logger.info("OK  %s", description)
                self.call_from_thread(self._show_command_status, f"OK: {description}")
            else:
                stderr = (result.stderr or "").strip()
                stdout = (result.output or "").strip()
                exc_msg = str(result.exception) if result.exception else ""
                err = _extract_error_message(stderr, stdout, exc_msg)
                self._cmd_logger.error("FAIL  %s — %s", description, err)
                self.call_from_thread(self._show_command_status, f"FAIL: {description} — {err}")

            await asyncio.sleep(5)
            self.call_from_thread(self._hide_command_status)

        self.run_worker(_invoke, thread=True, exclusive=False)  # type: ignore[arg-type]

    # -- Quit (signals shutdown to serve.py) -----------------------------------

    async def action_quit(self) -> None:
        """Quit the TUI and signal the serve loop to shut down."""
        self._cmd_logger.info("QUIT user requested shutdown")
        self._cleanup_activity_handler()
        self._show_command_status("Shutting down...")
        self.shutdown_event.set()
        self.exit()

    # -- Help screen -----------------------------------------------------------

    def action_help(self) -> None:
        server_parts: list[str] = []
        if self._mcp_url:
            server_parts.append(f"MCP: {self._mcp_url}")
        if self._tunnel_url:
            server_parts.append(f"Tunnel: {self._tunnel_url}")
        log_paths = ""
        if self._log_path:
            log_paths += f"CSV log: {self._log_path}\n"
        cmd_log = getattr(self, "_cmd_log_path", "")
        if cmd_log:
            log_paths += f"Command log: {cmd_log}\n"
        if self._activity_log_path:
            log_paths += f"Activity log: {self._activity_log_path}\n"
        self.push_screen(
            HelpScreen(log_path=log_paths.rstrip(), server_info="  ".join(server_parts))
        )

    # -- Command palette (Ctrl+P) -----------------------------------------------

    def get_system_commands(self, screen: Screen[Any]) -> Iterable[SystemCommand]:
        """Populate the command palette with all vehicle commands."""
        yield from super().get_system_commands(screen)

        # --- Security ---
        yield SystemCommand("Lock doors", "Lock all doors", self.action_cmd_lock)
        yield SystemCommand("Unlock doors", "Unlock all doors", self.action_cmd_unlock)
        yield SystemCommand("Honk horn", "Honk the horn", self.action_cmd_honk)
        yield SystemCommand("Flash lights", "Flash headlights", self.action_cmd_flash)
        yield SystemCommand("Sentry mode on", "Enable sentry mode", self.action_cmd_sentry_on)
        yield SystemCommand("Sentry mode off", "Disable sentry mode", self.action_cmd_sentry_off)
        yield SystemCommand("Remote start", "Enable keyless driving", self.action_cmd_remote_start)
        yield SystemCommand("Valet mode on", "Enable valet mode", self.action_cmd_valet_on)
        yield SystemCommand("Valet mode off", "Disable valet mode", self.action_cmd_valet_off)
        yield SystemCommand("Valet PIN reset", "Reset valet mode PIN", self.action_cmd_valet_reset)
        yield SystemCommand(
            "Auto-secure", "Auto-lock and close windows", self.action_cmd_auto_secure
        )
        yield SystemCommand(
            "PIN to Drive on", "Enable PIN to Drive", self.action_cmd_pin_to_drive_on
        )
        yield SystemCommand(
            "PIN to Drive off", "Disable PIN to Drive", self.action_cmd_pin_to_drive_off
        )
        yield SystemCommand("Guest mode on", "Enable guest mode", self.action_cmd_guest_on)
        yield SystemCommand("Guest mode off", "Disable guest mode", self.action_cmd_guest_off)
        yield SystemCommand(
            "Boombox", "Play boombox sound", self.action_cmd_boombox, discover=False
        )
        yield SystemCommand(
            "Speed limit clear (admin)",
            "Admin clear speed limit",
            self.action_cmd_speed_clear_admin,
            discover=False,
        )

        # --- Charging ---
        yield SystemCommand(
            "Start charging", "Begin charging session", self.action_cmd_charge_start
        )
        yield SystemCommand("Stop charging", "Stop charging session", self.action_cmd_charge_stop)
        yield SystemCommand(
            "Open charge port", "Open the charge port door", self.action_cmd_port_open
        )
        yield SystemCommand(
            "Close charge port", "Close the charge port door", self.action_cmd_port_close
        )
        yield SystemCommand(
            "Charge limit: max range",
            "Set charge limit to 100%",
            self.action_cmd_charge_max,
        )
        yield SystemCommand(
            "Charge limit: standard",
            "Set charge limit to standard (80%)",
            self.action_cmd_charge_std,
        )
        yield SystemCommand(
            "Charge limit: 50%",
            "Set charge limit to 50%",
            lambda: self._run_command(["charge", "limit", "50"], "Charge limit 50%"),
        )
        yield SystemCommand(
            "Charge limit: 60%",
            "Set charge limit to 60%",
            lambda: self._run_command(["charge", "limit", "60"], "Charge limit 60%"),
        )
        yield SystemCommand(
            "Charge limit: 70%",
            "Set charge limit to 70%",
            lambda: self._run_command(["charge", "limit", "70"], "Charge limit 70%"),
        )
        yield SystemCommand(
            "Charge limit: 80%",
            "Set charge limit to 80%",
            lambda: self._run_command(["charge", "limit", "80"], "Charge limit 80%"),
        )
        yield SystemCommand(
            "Charge limit: 90%",
            "Set charge limit to 90%",
            lambda: self._run_command(["charge", "limit", "90"], "Charge limit 90%"),
        )
        yield SystemCommand(
            "Charge amps: 8A",
            "Set charge amps to 8",
            lambda: self._run_command(["charge", "amps", "8"], "Charge amps 8A"),
        )
        yield SystemCommand(
            "Charge amps: 16A",
            "Set charge amps to 16",
            lambda: self._run_command(["charge", "amps", "16"], "Charge amps 16A"),
        )
        yield SystemCommand(
            "Charge amps: 24A",
            "Set charge amps to 24",
            lambda: self._run_command(["charge", "amps", "24"], "Charge amps 24A"),
        )
        yield SystemCommand(
            "Charge amps: 32A",
            "Set charge amps to 32",
            lambda: self._run_command(["charge", "amps", "32"], "Charge amps 32A"),
        )
        yield SystemCommand(
            "Charge amps: 48A",
            "Set charge amps to 48",
            lambda: self._run_command(["charge", "amps", "48"], "Charge amps 48A"),
        )
        yield SystemCommand(
            "Scheduled charging on",
            "Enable scheduled charging",
            self.action_cmd_charge_schedule_on,
        )
        yield SystemCommand(
            "Scheduled charging off",
            "Disable scheduled charging",
            self.action_cmd_charge_schedule_off,
        )

        # --- Climate ---
        yield SystemCommand("Climate on", "Turn on climate control", self.action_cmd_climate_on)
        yield SystemCommand("Climate off", "Turn off climate control", self.action_cmd_climate_off)
        yield SystemCommand(
            "Steering wheel heater on",
            "Enable steering wheel heater",
            self.action_cmd_wheel_heater_on,
        )
        yield SystemCommand(
            "Steering wheel heater off",
            "Disable steering wheel heater",
            self.action_cmd_wheel_heater_off,
        )
        yield SystemCommand(
            "Preconditioning on",
            "Enable battery preconditioning",
            self.action_cmd_precondition_on,
        )
        yield SystemCommand(
            "Preconditioning off",
            "Disable battery preconditioning",
            self.action_cmd_precondition_off,
        )
        yield SystemCommand(
            "Cabin overheat protection on",
            "Enable cabin overheat protection",
            self.action_cmd_overheat_on,
        )
        yield SystemCommand(
            "Cabin overheat protection off",
            "Disable cabin overheat protection",
            self.action_cmd_overheat_off,
        )
        yield SystemCommand(
            "Bioweapon defense on",
            "Enable bioweapon defense mode",
            self.action_cmd_bioweapon_on,
        )
        yield SystemCommand(
            "Bioweapon defense off",
            "Disable bioweapon defense mode",
            self.action_cmd_bioweapon_off,
        )
        yield SystemCommand(
            "Auto steering wheel heater on",
            "Enable auto steering wheel heater",
            self.action_cmd_auto_wheel_on,
        )
        yield SystemCommand(
            "Auto steering wheel heater off",
            "Disable auto steering wheel heater",
            self.action_cmd_auto_wheel_off,
        )
        yield SystemCommand("Defrost on", "Enable max defrost", self.action_cmd_defrost_on)
        yield SystemCommand("Defrost off", "Disable max defrost", self.action_cmd_defrost_off)
        yield SystemCommand(
            "Rear defrost on",
            "Enable rear window defrost",
            lambda: self._run_command(["climate", "set", "--rear-defrost-on"], "Rear defrost on"),
        )
        yield SystemCommand(
            "Rear defrost off",
            "Disable rear window defrost",
            lambda: self._run_command(
                ["climate", "set", "--rear-defrost-off"], "Rear defrost off"
            ),
        )
        yield SystemCommand(
            "Set cabin temp 68°F / 20°C",
            "Set driver and passenger temp to 68°F",
            lambda: self._run_command(
                ["climate", "set", "--driver-temp", "20", "--passenger-temp", "20"],
                "Cabin temp 20°C",
            ),
        )
        yield SystemCommand(
            "Set cabin temp 72°F / 22°C",
            "Set driver and passenger temp to 72°F",
            lambda: self._run_command(
                ["climate", "set", "--driver-temp", "22", "--passenger-temp", "22"],
                "Cabin temp 22°C",
            ),
        )
        yield SystemCommand(
            "Set cabin temp 75°F / 24°C",
            "Set driver and passenger temp to 75°F",
            lambda: self._run_command(
                ["climate", "set", "--driver-temp", "24", "--passenger-temp", "24"],
                "Cabin temp 24°C",
            ),
        )
        yield SystemCommand(
            "Seat heater: driver high",
            "Set driver seat heater to high",
            lambda: self._run_command(
                ["climate", "seat", "driver", "3"], "Driver seat heater high"
            ),
        )
        yield SystemCommand(
            "Seat heater: driver off",
            "Turn off driver seat heater",
            lambda: self._run_command(
                ["climate", "seat", "driver", "0"], "Driver seat heater off"
            ),
        )
        yield SystemCommand(
            "Seat heater: passenger high",
            "Set passenger seat heater to high",
            lambda: self._run_command(
                ["climate", "seat", "passenger", "3"],
                "Passenger seat heater high",
            ),
        )
        yield SystemCommand(
            "Seat heater: passenger off",
            "Turn off passenger seat heater",
            lambda: self._run_command(
                ["climate", "seat", "passenger", "0"], "Passenger seat heater off"
            ),
        )
        yield SystemCommand(
            "Auto seat climate: driver on",
            "Enable driver auto seat climate",
            lambda: self._run_command(
                ["climate", "auto-seat", "driver", "--on"], "Auto seat driver on"
            ),
        )
        yield SystemCommand(
            "Auto seat climate: driver off",
            "Disable driver auto seat climate",
            lambda: self._run_command(
                ["climate", "auto-seat", "driver", "--off"], "Auto seat driver off"
            ),
        )
        yield SystemCommand(
            "Climate keeper: Dog mode",
            "Set climate keeper to Dog mode",
            lambda: self._run_command(["climate", "keeper", "dog"], "Climate keeper: Dog"),
        )
        yield SystemCommand(
            "Climate keeper: Camp mode",
            "Set climate keeper to Camp mode",
            lambda: self._run_command(["climate", "keeper", "camp"], "Climate keeper: Camp"),
        )
        yield SystemCommand(
            "Climate keeper: off",
            "Turn off climate keeper mode",
            lambda: self._run_command(["climate", "keeper", "off"], "Climate keeper: off"),
        )
        yield SystemCommand(
            "Cabin overheat temp: low",
            "Set overheat protection temp to low (90°F/32°C)",
            lambda: self._run_command(["climate", "cop-temp", "low"], "Overheat temp: low"),
        )
        yield SystemCommand(
            "Cabin overheat temp: medium",
            "Set overheat protection temp to medium (100°F/38°C)",
            lambda: self._run_command(["climate", "cop-temp", "medium"], "Overheat temp: medium"),
        )
        yield SystemCommand(
            "Cabin overheat temp: high",
            "Set overheat protection temp to high (110°F/43°C)",
            lambda: self._run_command(["climate", "cop-temp", "high"], "Overheat temp: high"),
        )

        # --- Trunk & Windows ---
        yield SystemCommand("Open trunk", "Open/close rear trunk", self.action_cmd_trunk)
        yield SystemCommand("Close trunk", "Close rear trunk", self.action_cmd_trunk_close)
        yield SystemCommand("Open frunk", "Open front trunk", self.action_cmd_frunk)
        yield SystemCommand("Vent windows", "Vent all windows", self.action_cmd_window_vent)
        yield SystemCommand("Close windows", "Close all windows", self.action_cmd_window_close)
        yield SystemCommand("Vent sunroof", "Vent the sunroof", self.action_cmd_sunroof_vent)
        yield SystemCommand("Close sunroof", "Close the sunroof", self.action_cmd_sunroof_close)
        yield SystemCommand("Open tonneau", "Open the tonneau cover", self.action_cmd_tonneau_open)
        yield SystemCommand(
            "Close tonneau", "Close the tonneau cover", self.action_cmd_tonneau_close
        )
        yield SystemCommand("Stop tonneau", "Stop tonneau movement", self.action_cmd_tonneau_stop)

        # --- Media ---
        yield SystemCommand("Play / Pause", "Toggle media playback", self.action_cmd_play_pause)
        yield SystemCommand("Next track", "Skip to next track", self.action_cmd_next_track)
        yield SystemCommand("Previous track", "Go to previous track", self.action_cmd_prev_track)
        yield SystemCommand("Next favorite", "Skip to next favorite", self.action_cmd_next_fav)
        yield SystemCommand(
            "Previous favorite", "Go to previous favorite", self.action_cmd_prev_fav
        )
        yield SystemCommand("Volume up", "Increase volume", self.action_cmd_vol_up)
        yield SystemCommand("Volume down", "Decrease volume", self.action_cmd_vol_down)
        yield SystemCommand(
            "Volume: mute (0)",
            "Set volume to 0",
            lambda: self._run_command(["media", "adjust-volume", "0"], "Volume 0"),
        )
        yield SystemCommand(
            "Volume: 25%",
            "Set volume to 25%",
            lambda: self._run_command(["media", "adjust-volume", "2.75"], "Volume 25%"),
        )
        yield SystemCommand(
            "Volume: 50%",
            "Set volume to 50%",
            lambda: self._run_command(["media", "adjust-volume", "5.5"], "Volume 50%"),
        )

        # --- Navigation ---
        yield SystemCommand(
            "Navigate to Supercharger",
            "Navigate to nearest Supercharger",
            self.action_cmd_nav_supercharger,
        )
        yield SystemCommand(
            "Trigger HomeLink",
            "Trigger HomeLink (garage door)",
            self.action_cmd_nav_homelink,
        )
        yield SystemCommand(
            "Navigation: get GPS position",
            "Read current vehicle GPS coordinates",
            lambda: self._run_command(["nav", "gps"], "GPS position"),
        )

        # --- Software ---
        yield SystemCommand(
            "Cancel software update",
            "Cancel a pending software update",
            self.action_cmd_software_cancel,
        )
        yield SystemCommand(
            "Schedule software update now",
            "Schedule software update to install in 60s",
            lambda: self._run_command(["software", "schedule", "60"], "Schedule software update"),
        )

        # --- Vehicle ---
        yield SystemCommand("Wake vehicle", "Wake the vehicle from sleep", self.action_cmd_wake)
        yield SystemCommand(
            "Low power mode on",
            "Enable low power consumption mode",
            self.action_cmd_low_power_on,
        )
        yield SystemCommand(
            "Low power mode off",
            "Disable low power consumption mode",
            self.action_cmd_low_power_off,
        )
        yield SystemCommand(
            "Accessory power on",
            "Enable accessory power mode",
            self.action_cmd_accessory_power_on,
        )
        yield SystemCommand(
            "Accessory power off",
            "Disable accessory power mode",
            self.action_cmd_accessory_power_off,
        )
        yield SystemCommand(
            "Mobile access on",
            "Enable mobile app access",
            lambda: self._run_command(["vehicle", "mobile-access", "--on"], "Mobile access on"),
        )
        yield SystemCommand(
            "Mobile access off",
            "Disable mobile app access",
            lambda: self._run_command(["vehicle", "mobile-access", "--off"], "Mobile access off"),
        )

        # --- Sharing ---
        yield SystemCommand(
            "List driver invites",
            "List all sharing invitations",
            lambda: self._run_command(["sharing", "list-invites"], "List invites"),
        )

    # -- Security actions ------------------------------------------------------

    def action_cmd_lock(self) -> None:
        self._run_command(["security", "lock"], "Lock doors")

    def action_cmd_unlock(self) -> None:
        self._run_command(["security", "unlock"], "Unlock doors")

    def action_cmd_honk(self) -> None:
        self._run_command(["security", "honk"], "Honk horn")

    def action_cmd_flash(self) -> None:
        self._run_command(["security", "flash"], "Flash lights")

    def action_cmd_sentry_on(self) -> None:
        self._run_command(["security", "sentry", "--on"], "Sentry mode on")

    def action_cmd_sentry_off(self) -> None:
        self._run_command(["security", "sentry", "--off"], "Sentry mode off")

    def action_cmd_remote_start(self) -> None:
        self._run_command(["security", "remote-start"], "Remote start")

    def action_cmd_valet_on(self) -> None:
        self._run_command(["security", "valet", "--on"], "Valet mode on")

    def action_cmd_valet_off(self) -> None:
        self._run_command(["security", "valet", "--off"], "Valet mode off")

    def action_cmd_valet_reset(self) -> None:
        self._run_command(["security", "valet-reset"], "Valet pin reset")

    def action_cmd_auto_secure(self) -> None:
        self._run_command(["security", "auto-secure"], "Auto secure")

    def action_cmd_pin_to_drive_on(self) -> None:
        self._run_command(["security", "pin-to-drive", "--on"], "PIN to drive on")

    def action_cmd_pin_to_drive_off(self) -> None:
        self._run_command(["security", "pin-to-drive", "--off"], "PIN to drive off")

    def action_cmd_guest_on(self) -> None:
        self._run_command(["security", "guest-mode", "--on"], "Guest mode on")

    def action_cmd_guest_off(self) -> None:
        self._run_command(["security", "guest-mode", "--off"], "Guest mode off")

    def action_cmd_boombox(self) -> None:
        self._run_command(["security", "boombox"], "Boombox")

    def action_cmd_speed_clear_admin(self) -> None:
        self._run_command(["security", "speed-clear-admin"], "Speed limit clear (admin)")

    # -- Charging actions ------------------------------------------------------

    def action_cmd_charge_start(self) -> None:
        self._run_command(["charge", "start"], "Start charging")

    def action_cmd_charge_stop(self) -> None:
        self._run_command(["charge", "stop"], "Stop charging")

    def action_cmd_port_open(self) -> None:
        self._run_command(["charge", "port-open"], "Open charge port")

    def action_cmd_port_close(self) -> None:
        self._run_command(["charge", "port-close"], "Close charge port")

    def action_cmd_charge_max(self) -> None:
        self._run_command(["charge", "limit-max"], "Charge limit max")

    def action_cmd_charge_std(self) -> None:
        self._run_command(["charge", "limit-std"], "Charge limit standard")

    def action_cmd_charge_schedule_on(self) -> None:
        self._run_command(["charge", "schedule", "--enable"], "Charge schedule on")

    def action_cmd_charge_schedule_off(self) -> None:
        self._run_command(["charge", "schedule", "--disable"], "Charge schedule off")

    # -- Climate actions -------------------------------------------------------

    def action_cmd_climate_on(self) -> None:
        self._run_command(["climate", "on"], "Climate on")

    def action_cmd_climate_off(self) -> None:
        self._run_command(["climate", "off"], "Climate off")

    def action_cmd_wheel_heater_on(self) -> None:
        self._run_command(["climate", "wheel-heater", "--on"], "Wheel heater on")

    def action_cmd_wheel_heater_off(self) -> None:
        self._run_command(["climate", "wheel-heater", "--off"], "Wheel heater off")

    def action_cmd_precondition_on(self) -> None:
        self._run_command(["climate", "precondition", "--on"], "Precondition on")

    def action_cmd_precondition_off(self) -> None:
        self._run_command(["climate", "precondition", "--off"], "Precondition off")

    def action_cmd_overheat_on(self) -> None:
        self._run_command(["climate", "overheat", "--on"], "Overheat protection on")

    def action_cmd_overheat_off(self) -> None:
        self._run_command(["climate", "overheat", "--off"], "Overheat protection off")

    def action_cmd_bioweapon_on(self) -> None:
        self._run_command(["climate", "bioweapon", "--on"], "Bioweapon defense on")

    def action_cmd_bioweapon_off(self) -> None:
        self._run_command(["climate", "bioweapon", "--off"], "Bioweapon defense off")

    def action_cmd_auto_wheel_on(self) -> None:
        self._run_command(["climate", "auto-wheel", "--on"], "Auto wheel heater on")

    def action_cmd_auto_wheel_off(self) -> None:
        self._run_command(["climate", "auto-wheel", "--off"], "Auto wheel heater off")

    def action_cmd_defrost_on(self) -> None:
        self._run_command(["climate", "set", "--defrost-on"], "Defrost on")

    def action_cmd_defrost_off(self) -> None:
        self._run_command(["climate", "set", "--defrost-off"], "Defrost off")

    # -- Trunk actions ---------------------------------------------------------

    def action_cmd_trunk(self) -> None:
        self._run_command(["trunk", "open"], "Trunk open/close")

    def action_cmd_trunk_close(self) -> None:
        self._run_command(["trunk", "close"], "Trunk close")

    def action_cmd_frunk(self) -> None:
        self._run_command(["trunk", "frunk"], "Frunk open")

    def action_cmd_window_vent(self) -> None:
        self._run_command(["trunk", "window", "--vent"], "Windows vent")

    def action_cmd_window_close(self) -> None:
        self._run_command(["trunk", "window", "--close"], "Windows close")

    def action_cmd_sunroof_vent(self) -> None:
        self._run_command(["trunk", "sunroof", "--state", "vent"], "Sunroof vent")

    def action_cmd_sunroof_close(self) -> None:
        self._run_command(["trunk", "sunroof", "--state", "close"], "Sunroof close")

    def action_cmd_tonneau_open(self) -> None:
        self._run_command(["trunk", "tonneau-open"], "Tonneau open")

    def action_cmd_tonneau_close(self) -> None:
        self._run_command(["trunk", "tonneau-close"], "Tonneau close")

    def action_cmd_tonneau_stop(self) -> None:
        self._run_command(["trunk", "tonneau-stop"], "Tonneau stop")

    # -- Media actions ---------------------------------------------------------

    def action_cmd_play_pause(self) -> None:
        self._run_command(["media", "play-pause"], "Play/Pause")

    def action_cmd_next_track(self) -> None:
        self._run_command(["media", "next-track"], "Next track")

    def action_cmd_prev_track(self) -> None:
        self._run_command(["media", "prev-track"], "Previous track")

    def action_cmd_next_fav(self) -> None:
        self._run_command(["media", "next-fav"], "Next favorite")

    def action_cmd_prev_fav(self) -> None:
        self._run_command(["media", "prev-fav"], "Previous favorite")

    def action_cmd_vol_up(self) -> None:
        self._run_command(["media", "volume-up"], "Volume up")

    def action_cmd_vol_down(self) -> None:
        self._run_command(["media", "volume-down"], "Volume down")

    # -- Navigation actions ----------------------------------------------------

    def action_cmd_nav_supercharger(self) -> None:
        self._run_command(["nav", "supercharger"], "Navigate to Supercharger")

    def action_cmd_nav_homelink(self) -> None:
        self._run_command(["nav", "homelink"], "HomeLink trigger")

    # -- Software actions ------------------------------------------------------

    def action_cmd_software_cancel(self) -> None:
        self._run_command(["software", "cancel"], "Cancel software update")

    # -- Vehicle actions -------------------------------------------------------

    def action_cmd_wake(self) -> None:
        self._run_command(["vehicle", "wake", "--wait"], "Wake vehicle")

    def action_cmd_low_power_on(self) -> None:
        self._run_command(["vehicle", "low-power", "--on"], "Low power mode on")

    def action_cmd_low_power_off(self) -> None:
        self._run_command(["vehicle", "low-power", "--off"], "Low power mode off")

    def action_cmd_accessory_power_on(self) -> None:
        self._run_command(["vehicle", "accessory-power", "--on"], "Accessory power on")

    def action_cmd_accessory_power_off(self) -> None:
        self._run_command(["vehicle", "accessory-power", "--off"], "Accessory power off")


# ---------------------------------------------------------------------------
# Value formatting (ported from dashboard.py)
# ---------------------------------------------------------------------------


def _relative_path(url: str, tunnel_url: str) -> str:
    """Reduce a full URL to a relative port/path when a tunnel is active.

    If the URL shares the same scheme+host as *tunnel_url*, show only the
    path portion.  Otherwise fall back to ``:port/path`` for localhost URLs,
    or the full URL as-is.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if tunnel_url:
        tunnel_parsed = urlparse(tunnel_url)
        if parsed.hostname == tunnel_parsed.hostname:
            return parsed.path or "/"
    # Localhost — show :port/path.
    if parsed.hostname in ("127.0.0.1", "localhost", "::1"):
        return f":{parsed.port}{parsed.path}" if parsed.port else parsed.path or "/"
    return url


def _extract_error_message(stderr: str, stdout: str, exc_msg: str = "") -> str:
    """Extract a human-readable error from CLI output.

    When the TUI runs commands via CliRunner, exceptions are caught by Click
    and stored in ``result.exception`` rather than being formatted by
    ``main()``'s error handler.  The *exc_msg* parameter (from
    ``str(result.exception)``) is the most reliable error source.

    Falls back to parsing JSON error envelopes from stderr, then the last
    non-httpx line, then raw stderr/stdout.
    """
    import json

    # Best source: the exception message from Click's runner.
    if exc_msg:
        return exc_msg[:120]

    # Try each line of stderr for a JSON error envelope.
    for line in stderr.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                err = data.get("error", {})
                msg = err.get("message", "") if isinstance(err, dict) else str(err)
                if msg:
                    return msg[:120]
            except json.JSONDecodeError:
                continue

    # Fall back: last non-empty line of stderr, filtering out httpx INFO lines.
    for line in reversed(stderr.splitlines()):
        line = line.strip()
        if line and "HTTP Request:" not in line and "HTTP/1.1" not in line:
            return line[:120]

    return (stderr or stdout)[:80]


def _format_value(
    field_name: str,
    value: Any,
    units: DisplayUnits | None,
) -> str:
    """Format a telemetry value with optional unit conversion."""
    if value is None:
        return "—"

    if isinstance(value, dict):
        lat = value.get("latitude", 0.0)
        lng = value.get("longitude", 0.0)
        return f"{lat:.6f}, {lng:.6f}"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if units is not None:
        return _format_with_units(field_name, value, units)

    # No unit preferences — raw value.
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


_TEMP_FIELDS = frozenset(
    {
        "InsideTemp",
        "OutsideTemp",
        "HvacLeftTemperatureRequest",
        "HvacRightTemperatureRequest",
        "ModuleTempMax",
        "ModuleTempMin",
    }
)
_DISTANCE_FIELDS = frozenset(
    {
        "Odometer",
        "EstBatteryRange",
        "IdealBatteryRange",
        "RatedRange",
        "MilesToArrival",
    }
)
_SPEED_FIELDS = frozenset({"VehicleSpeed", "CruiseSetSpeed", "CurrentLimitMph"})
_PRESSURE_FIELDS = frozenset(
    {
        "TpmsPressureFl",
        "TpmsPressureFr",
        "TpmsPressureRl",
        "TpmsPressureRr",
    }
)
_PCT_FIELDS = frozenset({"Soc", "BatteryLevel", "ChargeLimitSoc"})


def _format_with_units(field_name: str, value: Any, units: DisplayUnits) -> str:
    """Apply unit conversion based on user preferences."""
    from tescmd.output.rich_output import DistanceUnit, PressureUnit, TempUnit

    if field_name in _TEMP_FIELDS and isinstance(value, (int, float)):
        if units.temp == TempUnit.F:
            return f"{value * 9 / 5 + 32:.1f}\u00b0F"
        return f"{value:.1f}\u00b0C"

    if field_name in _DISTANCE_FIELDS and isinstance(value, (int, float)):
        if units.distance == DistanceUnit.KM:
            return f"{value * 1.60934:.1f} km"
        return f"{value:.1f} mi"

    if field_name in _SPEED_FIELDS and isinstance(value, (int, float)):
        if units.distance == DistanceUnit.KM:
            return f"{value * 1.60934:.0f} km/h"
        return f"{value:.0f} mph"

    if field_name in _PRESSURE_FIELDS and isinstance(value, (int, float)):
        if units.pressure == PressureUnit.PSI:
            return f"{value * 14.5038:.1f} psi"
        return f"{value:.2f} bar"

    if field_name in _PCT_FIELDS and isinstance(value, (int, float)):
        return f"{value}%"

    # Voltage / current.
    if "Voltage" in field_name and isinstance(value, (int, float)):
        return f"{value:.1f} V"
    if ("Current" in field_name or "Amps" in field_name) and isinstance(value, (int, float)):
        return f"{value:.1f} A"

    # Power.
    if "Power" in field_name and isinstance(value, (int, float)):
        return f"{value:.2f} kW"

    # Time-to-full.
    if field_name == "TimeToFullCharge" and isinstance(value, (int, float)):
        hours = int(value)
        mins = int((value - hours) * 60)
        return f"{hours}h {mins}m" if hours else f"{mins}m"

    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
