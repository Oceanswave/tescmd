# CLAUDE.md — Project Context for Claude Code

## Project Overview

**tescmd** is a Python CLI application that queries data from and sends commands to Tesla vehicles via the [Tesla Fleet API](https://developer.tesla.com/docs/fleet-api). The current implementation covers OAuth2 authentication, key management, vehicle state queries (battery, location, climate, drive state, tire pressure, trunks, and more), and both human-friendly (Rich TUI) and machine-friendly (JSON) output with configurable display units.

**Current scope:** auth, vehicle queries, vehicle commands (charge, climate, security, trunk, media, nav, software), energy product management, user account info, vehicle sharing, key management with enrollment, Vehicle Command Protocol (ECDH sessions + HMAC-signed commands), tier enforcement, initial setup, response caching with cost-aware wake confirmation, and Fleet Telemetry awareness.

## Tech Stack

- **Python 3.11+** (required for `tomllib`, `StrEnum`, modern typing)
- **pydantic v2** — request/response models, settings management
- **rich** — terminal tables, panels, spinners, progress bars
- **click** — CLI argument parsing and command routing
- **httpx** — async HTTP client for Fleet API calls
- **cryptography** — EC key generation, PEM handling, ECDH key exchange
- **protobuf** — protobuf serialization for Vehicle Command Protocol messages
- **keyring** — OS-level credential storage for tokens
- **python-dotenv** — `.env` file loading
- **bleak** — BLE communication for key enrollment (optional; portal enrollment is primary)

## Project Structure

```
src/tescmd/
├── __init__.py            # Package version
├── __main__.py            # Entry point (python -m tescmd)
├── cli/                   # CLI layer (click-based)
│   ├── __init__.py
│   ├── main.py            # Root Click group, dispatch, AppContext
│   ├── _options.py        # Shared Click options/decorators
│   ├── _client.py         # API client builders, auto_wake, cached_vehicle_data
│   ├── auth.py            # auth login, auth logout, auth status, auth register
│   ├── cache.py           # cache clear, cache status
│   ├── charge.py          # charge status, start, stop, limit, amps, schedule, departure, precondition, managed-amps, add-schedule, remove-schedule
│   ├── climate.py         # climate status, on, off, set, seat, keeper, cop-temp, auto-seat, auto-wheel, wheel-level
│   ├── security.py        # security status, lock, unlock, sentry, valet, pin-reset, speed-clear, etc.
│   ├── trunk.py           # trunk open, close, frunk, window vent/close, sunroof vent/close/stop, tonneau open/close/stop
│   ├── vehicle.py         # vehicle list, info, data, location, wake, alerts, release-notes, service, drivers, low-power, accessory-power
│   ├── media.py           # media play-pause, next/prev track, next/prev fav, volume
│   ├── nav.py             # nav send, gps, supercharger, homelink, waypoints
│   ├── software.py        # software status, schedule, cancel
│   ├── energy.py          # energy list, status, live, backup, mode, storm, tou, history, off-grid, grid-config, calendar
│   ├── user.py            # user me, region, orders, features
│   ├── sharing.py         # sharing add/remove driver, create/redeem/revoke/list invites
│   ├── raw.py             # raw get, raw post (arbitrary Fleet API access)
│   ├── key.py             # key generate, deploy, validate, show, enroll
│   └── setup.py           # setup (interactive first-run wizard, key enrollment, Fleet Telemetry awareness)
├── api/                   # API client layer
│   ├── __init__.py
│   ├── client.py          # TeslaFleetClient (base HTTP client)
│   ├── vehicle.py         # VehicleAPI (vehicle data, nearby chargers, alerts, drivers)
│   ├── command.py         # CommandAPI (~76 vehicle commands, unsigned REST)
│   ├── signed_command.py  # SignedCommandAPI (Vehicle Command Protocol routing)
│   ├── energy.py          # EnergyAPI (Powerwall/energy product endpoints)
│   ├── sharing.py         # SharingAPI (driver and invite management)
│   ├── user.py            # UserAPI (account info, region, orders, features)
│   └── errors.py          # API error types (incl. TierError, SessionError, KeyNotEnrolledError)
├── cache/                 # Response caching
│   ├── __init__.py        # Re-exports ResponseCache
│   ├── response_cache.py  # ResponseCache (file-based JSON with TTL)
│   └── keys.py            # Cache key generation (VIN + endpoint hash)
├── models/                # Pydantic models
│   ├── __init__.py        # Re-exports all models (~42 symbols)
│   ├── vehicle.py         # Vehicle, VehicleData, DriveState, ChargeState, ClimateState, VehicleState, VehicleConfig, GuiSettings, SoftwareUpdateInfo, SuperchargerInfo, DestChargerInfo, NearbyChargingSites
│   ├── energy.py          # LiveStatus, SiteInfo, CalendarHistory, GridImportExportConfig
│   ├── user.py            # UserInfo, UserRegion, VehicleOrder, FeatureConfig
│   ├── sharing.py         # ShareDriverInfo, ShareInvite
│   ├── auth.py            # TokenResponse, AuthConfig
│   ├── command.py         # CommandResponse, CommandResult
│   └── config.py          # AppSettings (pydantic-settings, incl. cache settings)
├── auth/                  # Authentication
│   ├── __init__.py
│   ├── oauth.py           # OAuth2 PKCE flow, token refresh, partner registration
│   ├── token_store.py     # Keyring-backed token persistence
│   └── server.py          # Local callback server for OAuth redirect
├── protocol/              # Vehicle Command Protocol
│   ├── __init__.py        # Re-exports: Session, SessionManager, CommandSpec, etc.
│   ├── protobuf/          # Protobuf message definitions
│   │   ├── __init__.py
│   │   └── messages.py    # RoutableMessage, SessionInfo, Domain, SignatureData, etc.
│   ├── session.py         # ECDH session management (SessionManager)
│   ├── signer.py          # HMAC-SHA256 command signing
│   ├── metadata.py        # TLV serialization for command metadata
│   ├── commands.py        # Command registry (name → domain + signing requirement)
│   └── encoder.py         # RoutableMessage assembly + base64 encoding
├── crypto/                # Key management and ECDH
│   ├── __init__.py
│   ├── keys.py            # EC key generation, loading, PEM export
│   └── ecdh.py            # ECDH key exchange, session key derivation
├── output/                # Output formatting
│   ├── __init__.py
│   ├── formatter.py       # OutputFormatter (auto-detect TTY vs pipe)
│   ├── rich_output.py     # Rich tables, panels, status displays, DisplayUnits
│   └── json_output.py     # Structured JSON output
├── ble/                   # BLE communication (stub — enrollment not yet wired)
│   └── __init__.py
├── config/                # Configuration (stub — settings in models/config.py)
│   └── __init__.py
└── _internal/             # Shared utilities
    ├── __init__.py
    ├── vin.py             # Smart VIN resolution
    └── async_utils.py     # asyncio helpers (run_async)
```

### Key Models (`models/vehicle.py`)

The Pydantic vehicle models cover an extensive set of Tesla Fleet API fields:

- **ChargeState** — battery %, range (rated/ideal/estimated), usable %, charge limit, rate, voltage, current, charger power, charger type, energy added, cable type, port latch, scheduled charging, battery heater, preconditioning
- **ClimateState** — inside/outside temp, driver/passenger setting, HVAC on/off, fan speed, defrost, front+rear seat heaters, steering wheel heater, cabin overheat protection, bioweapon defense mode, auto conditioning, preconditioning
- **VehicleState** — locked, odometer, sentry mode, firmware version, doors (4), windows (4), frunk/trunk (ft/rt), center display, dashcam, remote start, user present, homelink, TPMS tire pressure (4 wheels)
- **VehicleConfig** — car type, trim, color, wheels, roof color, navigation, trunk actuation, seat cooling, motorized charge port, power liftgate, EU vehicle
- **GuiSettings** — distance units, temperature units, charge rate units

Additional typed models:

- **SoftwareUpdateInfo** — status, version, install_perc, expected_duration_sec, scheduled_time_ms, download_perc
- **NearbyChargingSites** — superchargers (list of SuperchargerInfo), destination_charging (list of DestChargerInfo)
- **SiteInfo** — energy_site_id, site_name, resource_type, backup_reserve_percent, default_real_mode, storm_mode_enabled
- **CalendarHistory** — serial_number, time_series
- **GridImportExportConfig** — disallow_charge_from_grid_with_solar_installed, customer_preferred_export_rule
- **VehicleOrder** — order_id, vin, model, status
- **FeatureConfig** — signaling dict
- **ShareDriverInfo** — share_user_id, email, status, public_key
- **ShareInvite** — id, code, created_at, expires_at, status

All models use `extra="allow"` so unknown fields from the API are captured without validation errors.

### Display Units (`output/rich_output.py`)

Rich output supports configurable display units via `DisplayUnits`:

- **Pressure:** PSI (default) or bar
- **Temperature:** °F (default) or °C
- **Distance:** mi (default) or km

The Tesla API returns temperatures in Celsius, distances in miles, and tire pressures in bar. Conversions happen in the display layer only — models retain raw API values.

```python
from tescmd.output.rich_output import DisplayUnits, DistanceUnit, PressureUnit, TempUnit

# US defaults (no argument needed)
ro = RichOutput(console)

# Metric
ro = RichOutput(console, units=DisplayUnits(
    pressure=PressureUnit.BAR,
    temp=TempUnit.C,
    distance=DistanceUnit.KM,
))
```

### Response Cache (`cache/response_cache.py`)

The Tesla Fleet API is pay-per-use — every call with status < 500 is billable, wake requests are the most expensive category (3/min limit), and their docs explicitly say `vehicle_data` should never be polled regularly. The response cache reduces API costs through three mechanisms:

1. **Disk cache** — `ResponseCache` stores API responses as JSON files under `~/.cache/tescmd/`. Each entry has a TTL (default 60s). Expired entries are cleaned up lazily on read.
2. **Wake state cache** — Tracks whether the vehicle was recently confirmed online (default 30s TTL). Skips redundant wake attempts when the vehicle is known to be awake.
3. **Wake confirmation prompt** — Before sending a billable wake API call, users are prompted interactively (TTY) or receive a structured error (JSON/piped) with guidance to wake via the Tesla app for free.

Cache files are named `{vin}_{endpoint_hash}.json` (data) or `{vin}_wake.json` (wake state). The VIN prefix enables per-vehicle clearing via glob.

**Data flow for read-commands** (`cached_vehicle_data()` in `_client.py`):

1. Check disk cache → on hit, return `VehicleData.model_validate(cached)`
2. Check wake state cache → if recently online, try direct API fetch (skip wake)
3. If direct fetch raises `VehicleAsleepError`, fall back to `auto_wake()`
4. If no cached wake state, use `auto_wake()` directly
5. On success, cache the response and update wake state

**Write-commands** (POST operations) do not cache responses but call `invalidate_cache_for_vin()` after success to prevent stale reads.

```python
from tescmd.cache import ResponseCache

cache = ResponseCache(cache_dir=Path("~/.cache/tescmd"), default_ttl=60, enabled=True)
cache.put("VIN123", {"charge_state": {"battery_level": 72}}, endpoints=["charge_state"])
data = cache.get("VIN123", endpoints=["charge_state"])  # dict or None
cache.put_wake_state("VIN123", "online", ttl=30)
is_online = cache.get_wake_state("VIN123")  # True/False
cache.clear("VIN123")  # per-VIN, or cache.clear() for all
```

### Wake Confirmation (`cli/_client.py`)

When a vehicle is asleep and a command needs to wake it, `auto_wake()` behaves differently based on context:

| Mode | `--wake` flag | Behavior |
|---|---|---|
| TTY (Rich) | Not set | Interactive prompt: `[W] Wake via API  [R] Retry  [C] Cancel` |
| TTY (Rich) | Set | Auto-wake without prompting |
| JSON / piped | Not set | Raise `VehicleAsleepError` with `--wake` guidance |
| JSON / piped | Set | Auto-wake without prompting |

The `[R] Retry` option allows users to wake the vehicle for free via the Tesla mobile app and then retry the command without a billable API call. If the vehicle is still asleep after retry, the prompt re-appears. The `vehicle wake` command is an explicit wake request and uses its own logic (no prompt needed). The wake state cache means the prompt only triggers when the vehicle is actually asleep — if it was recently confirmed online, the prompt is skipped entirely.

## Coding Conventions

- **Type hints everywhere** — all function signatures, all variables where non-obvious
- **async/await** — all API calls are async; CLI entry points use `run_async()` helper
- **Pydantic models** — all API request/response payloads; all configuration
- **src layout** — code lives under `src/tescmd/`, tests under `tests/`
- **No star imports** — explicit imports only
- **Single responsibility** — CLI modules handle args + output, API modules handle HTTP
- **Composition over inheritance** — `VehicleAPI` wraps `TeslaFleetClient`, doesn't extend it

## Build System

- **hatchling** via `pyproject.toml`
- Entry point: `tescmd = "tescmd.cli.main:main"`
- No `setup.py` or `setup.cfg`

## Testing

- **pytest** + **pytest-asyncio** + **pytest-httpx**
- Test files mirror source: `tests/cli/test_auth.py`, `tests/api/test_client.py`, etc.
- Use `pytest-httpx` to mock HTTP responses (no live API calls in tests)
- Async tests use `@pytest.mark.asyncio`
- Current count: ~897 tests

## Linting & Formatting

- **ruff** — linting and formatting (replaces flake8, isort, black)
- **mypy** — strict mode, all code fully typed
- Config in `pyproject.toml`

## Key Architectural Decisions

1. **Composition over inheritance** — API classes wrap `TeslaFleetClient` via constructor injection
2. **REST-first with portal key enrollment** — all commands go over REST; key enrollment uses Tesla Developer Portal (remote, confirmed via Tesla app); BLE enrollment is an optional alternative requiring physical proximity
3. **Output auto-detection** — TTY → Rich panels/tables; piped → JSON; `--quiet` → minimal stderr only
4. **Error output stream routing** — JSON/piped mode writes errors to **stderr** so stdout stays clean for machine-parseable data (scripts can safely `| jq`). TTY/Rich mode keeps errors on **stdout** because the user is looking at the terminal directly — splitting streams would be worse UX there. This split lives in `OutputFormatter.output_error()` and the error handlers in `cli/main.py`. Interactive prompts (wake confirmation spinner, enrollment approval) always use stdout via Rich since they are inherently TTY-only.
5. **Smart VIN resolution** — positional arg > `--vin` flag > profile default > interactive picker
6. **Settings resolution** — CLI args > env vars (`.env` loaded via python-dotenv) > `config.toml` profile > defaults
7. **click** — works well with command structure, async patterns
8. **httpx async** — clean async API, good type stubs, easily testable with pytest-httpx
9. **Browser-based auth** — `tescmd auth login` opens system browser for OAuth2 PKCE flow with local callback server
10. **Display-layer unit conversion** — models retain raw API values (Celsius, miles, bar); conversion to user-preferred units happens in `RichOutput` via `DisplayUnits`
11. **Response caching** — file-based JSON cache under `~/.cache/tescmd/` with per-entry TTL. Read-commands check cache first; write-commands invalidate after success. No new dependencies (stdlib `json`, `hashlib`, `time`, `pathlib`).
12. **Cost-aware wake** — `auto_wake()` prompts before sending billable wake API calls. TTY users get an interactive choice; JSON/piped consumers get structured errors. The `--wake` flag opts in to auto-wake for scripts that accept the cost.
13. **Smart wake state** — wake state is cached separately (30s TTL). If the vehicle was recently confirmed online, both the prompt and the wake API call are skipped entirely.
14. **Vehicle Command Protocol** — `SignedCommandAPI` wraps `CommandAPI` via composition. When keys are enrolled and tier is `full`, `get_command_api()` returns `SignedCommandAPI` which transparently routes signed commands through ECDH session + HMAC path. Unsigned commands (`wake_up`) pass through to legacy REST. The `command_protocol` setting (`auto`/`signed`/`unsigned`) controls routing.
15. **Tier enforcement** — `execute_command()` checks `setup_tier` before running write commands. Readonly tier raises `TierError` with guidance to upgrade via `tescmd setup`.
16. **Key enrollment** — `tescmd key enroll <VIN>` sends the public key to the vehicle via the unsigned `add_key_request` endpoint, then guides the user through Tesla app approval with an interactive prompt or `--wait` auto-polling.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TESLA_CLIENT_ID` | OAuth2 application client ID | — |
| `TESLA_CLIENT_SECRET` | OAuth2 application client secret | — |
| `TESLA_VIN` | Default vehicle VIN | — |
| `TESLA_REGION` | API region (`na`, `eu`, `cn`) | `na` |
| `TESLA_TOKEN_FILE` | Override token storage path | (keyring) |
| `TESLA_CONFIG_DIR` | Override config directory | `~/.config/tescmd` |
| `TESLA_OUTPUT_FORMAT` | Force output format (`rich`, `json`, `quiet`) | (auto) |
| `TESLA_PROFILE` | Active config profile name | `default` |
| `TESLA_CACHE_ENABLED` | Enable/disable response cache | `true` |
| `TESLA_CACHE_TTL` | Cache entry time-to-live (seconds) | `60` |
| `TESLA_CACHE_DIR` | Cache directory path | `~/.cache/tescmd` |
| `TESLA_COMMAND_PROTOCOL` | Command signing: `auto`, `signed`, `unsigned` | `auto` |

All variables can also be set in a `.env` file in the working directory or `$TESLA_CONFIG_DIR/.env`.

## CLI Flags

| Flag | Scope | Description |
|---|---|---|
| `--vin VIN` | Global | Vehicle VIN (also positional on most commands) |
| `--profile NAME` | Global | Config profile name |
| `--format {rich,json,quiet}` | Global | Force output format |
| `--quiet` | Global | Suppress normal output |
| `--region {na,eu,cn}` | Global | Tesla API region |
| `--verbose` | Global | Enable verbose logging |
| `--no-cache` / `--fresh` | Global | Bypass response cache for this invocation |
| `--wake` | Global | Auto-wake vehicle without confirmation (billable) |

All global flags can be specified at the root level (`tescmd --wake charge status`) or after the subcommand (`tescmd charge status --wake`).

## Common Commands (for reference)

```bash
# Dev
ruff check src/ tests/
ruff format src/ tests/
mypy src/
pytest
pytest tests/cli/ -k "test_auth"
pytest tests/cache/              # Cache-specific tests

# Build
python -m build

# Cache management
tescmd cache status              # Show cache stats
tescmd cache clear               # Clear all cached entries
tescmd cache clear --vin VIN     # Clear cache for a specific vehicle

# Cost-optimized usage
tescmd charge status             # Uses cache, prompts before wake
tescmd charge status --fresh     # Bypasses cache, still prompts before wake
tescmd charge status --wake      # Auto-wakes without prompting (billable)
```
