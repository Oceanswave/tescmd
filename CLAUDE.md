# CLAUDE.md — Project Context for Claude Code

## Project Overview

**tescmd** is a Python CLI application that queries data from and sends commands to Tesla vehicles via the [Tesla Fleet API](https://developer.tesla.com/docs/fleet-api). It covers the full API surface — vehicle state queries (location, battery, climate, drive state) and 80+ vehicle commands — with OAuth2 authentication, key management, and both human-friendly (Rich TUI) and machine-friendly (JSON) output.

## Tech Stack

- **Python 3.11+** (required for `tomllib`, `StrEnum`, modern typing)
- **pydantic v2** — request/response models, settings management
- **rich** — terminal tables, panels, spinners, progress bars
- **argparse** — CLI argument parsing (stdlib, no extra deps)
- **httpx** — async HTTP client for Fleet API calls
- **cryptography** — EC key generation, PEM handling, signing
- **keyring** — OS-level credential storage for tokens
- **python-dotenv** — `.env` file loading
- **bleak** — BLE communication for key enrollment (optional; portal enrollment is primary)

## Project Structure

```
src/tescmd/
├── __init__.py          # Package version
├── __main__.py          # Entry point (python -m tescmd)
├── cli/                 # CLI layer
│   ├── __init__.py
│   ├── main.py          # Root parser, dispatch
│   ├── auth.py          # auth login, auth logout, auth status
│   ├── vehicle.py       # vehicle list, vehicle info, vehicle data, vehicle location, vehicle wake
│   ├── charge.py        # charge status, charge start, charge stop, charge limit, etc.
│   ├── climate.py       # climate status, climate on, climate off, climate set, etc.
│   ├── security.py      # security status, lock, unlock, remote-start, speed-limit, etc.
│   ├── media.py         # media status, media play, pause, next, prev, volume
│   ├── nav.py           # nav set, nav waypoint, nav sc
│   ├── trunk.py         # trunk open, trunk close, frunk open
│   ├── software.py      # software status, software update, software cancel
│   ├── key.py           # key generate, key register, key list
│   ├── fleet.py         # fleet status, fleet telemetry
│   └── raw.py           # raw get, raw post (arbitrary endpoints)
├── api/                 # API client layer
│   ├── __init__.py
│   ├── client.py        # TeslaFleetClient (base HTTP client)
│   ├── vehicle.py       # VehicleAPI (vehicle endpoints)
│   ├── command.py       # CommandAPI (vehicle command endpoints)
│   ├── fleet.py         # FleetAPI (fleet-wide endpoints)
│   └── errors.py        # API error types
├── models/              # Pydantic models
│   ├── __init__.py
│   ├── vehicle.py       # Vehicle, VehicleData, DriveState, etc.
│   ├── auth.py          # TokenResponse, AuthConfig
│   ├── command.py       # CommandResponse, CommandResult
│   └── config.py        # AppConfig, Profile
├── auth/                # Authentication
│   ├── __init__.py
│   ├── oauth.py         # OAuth2 PKCE flow, token refresh
│   ├── token_store.py   # Keyring-backed token persistence
│   └── server.py        # Local callback server for OAuth redirect
├── crypto/              # Key management
│   ├── __init__.py
│   ├── keys.py          # EC key generation, loading, PEM export
│   └── signing.py       # Command signing for protocol v2
├── output/              # Output formatting
│   ├── __init__.py
│   ├── formatter.py     # OutputFormatter (auto-detect TTY vs pipe)
│   ├── rich_output.py   # Rich tables, panels, status displays
│   └── json_output.py   # Structured JSON output
├── config/              # Configuration
│   ├── __init__.py
│   ├── settings.py      # Pydantic Settings (env + file + CLI)
│   └── profiles.py      # Multi-profile management
├── ble/                 # BLE communication
│   ├── __init__.py
│   └── enroll.py        # BLE key enrollment via bleak
└── _internal/           # Shared utilities
    ├── __init__.py
    ├── vin.py           # Smart VIN resolution
    └── async_utils.py   # asyncio helpers
```

## Coding Conventions

- **Type hints everywhere** — all function signatures, all variables where non-obvious
- **async/await** — all API calls are async; CLI entry points use `asyncio.run()`
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

## Linting & Formatting

- **ruff** — linting and formatting (replaces flake8, isort, black)
- **mypy** — strict mode, all code fully typed
- Config in `pyproject.toml`

## Key Architectural Decisions

1. **Composition over inheritance** — API classes wrap `TeslaFleetClient` via constructor injection
2. **REST-first with portal key enrollment** — all commands go over REST; key enrollment uses Tesla Developer Portal (remote, confirmed via Tesla app); BLE enrollment is an optional alternative requiring physical proximity
3. **Output auto-detection** — TTY → Rich panels/tables; piped → JSON; `--quiet` → minimal stderr only
4. **Smart VIN resolution** — positional arg > `--vin` flag > profile default > interactive picker
5. **Settings resolution** — CLI args > env vars (`.env` loaded via python-dotenv) > `config.toml` profile > defaults
6. **argparse over click/typer** — stdlib, no extra dependencies, works well with async patterns
7. **httpx async** — clean async API, good type stubs, easily testable with pytest-httpx
8. **Browser-based auth** — `tescmd auth login` opens system browser for OAuth2 PKCE flow with local callback server

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

All variables can also be set in a `.env` file in the working directory or `$TESLA_CONFIG_DIR/.env`.

## Common Commands (for reference)

```bash
# Dev
ruff check src/ tests/
ruff format src/ tests/
mypy src/
pytest
pytest tests/cli/ -k "test_auth"

# Build
python -m build
```
