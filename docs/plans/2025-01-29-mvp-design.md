# MVP Design: Auth + Vehicle Data Vertical Slice

**Date:** 2025-01-29
**Goal:** End-to-end working CLI — authenticate via browser OAuth, query vehicle list, get vehicle location.

## MVP Milestone

```bash
tescmd auth login        # opens browser, OAuth2 PKCE, stores tokens
tescmd vehicle list      # shows vehicles on account
tescmd vehicle location  # returns GPS coordinates for default vehicle
```

This cuts vertically through every architectural layer: config → auth → HTTP client → API → CLI → output.

## Scope

### In Scope

| Layer | Modules | Details |
|-------|---------|---------|
| Build | `pyproject.toml` | hatchling, all deps, ruff/mypy/pytest config |
| Package | `__init__.py`, `__main__.py` | Version, entry point |
| Config | `config/settings.py`, `config/profiles.py` | pydantic-settings, `.env` loading, TOML profiles, settings resolution (CLI > env > config > defaults) |
| Models | `models/vehicle.py`, `models/auth.py`, `models/command.py`, `models/config.py` | Vehicle, VehicleData, DriveState, ChargeState, ClimateState, VehicleState, TokenResponse, AuthConfig, AppConfig, Profile |
| Auth | `auth/oauth.py`, `auth/server.py`, `auth/token_store.py` | OAuth2 PKCE flow, local callback server, keyring storage, token refresh |
| Client | `api/client.py`, `api/errors.py` | httpx async, auth headers, regional base URLs, 401→refresh→retry, typed exceptions |
| API | `api/vehicle.py` | VehicleAPI: list, info, data, location (via get_vehicle_data with drive_state endpoint) |
| CLI | `cli/main.py`, `cli/auth.py`, `cli/vehicle.py` | Root parser + dispatch, auth commands (login/logout/status/refresh/export/import), vehicle commands (list/info/data/location/wake) |
| Output | `output/formatter.py`, `output/rich_output.py`, `output/json_output.py` | TTY auto-detect, Rich tables/panels, JSON envelope |
| Internal | `_internal/vin.py`, `_internal/async_utils.py` | Smart VIN resolution, asyncio helpers |
| Tests | Core paths | Settings resolution, client with mocked HTTP, auth flow, vehicle list/location output |

### Out of Scope (Post-MVP)

- Command groups: charge, climate, security, media, nav, trunk, software, fleet, raw
- Key management: crypto/, cli/key.py, portal enrollment
- BLE enrollment: ble/
- `--verbose` debug logging
- Integration / end-to-end tests
- Rich output polish beyond functional tables/panels

## Architecture Decisions (confirmed)

1. **Bot/automation primary use case** — JSON output, exit codes, headless auth are first-class
2. **Both Rich + JSON from day one** — humans and bots both served
3. **Portal enrollment primary** (post-MVP) — BLE is optional alternative
4. **Core-paths testing** — auth, client, vehicle data; fill in breadth later
5. **All command groups planned** — MVP is vertical slice; post-MVP expands horizontally

## Build Order

### Phase A: Foundation (no API calls)

1. `pyproject.toml` — hatchling build, all dependencies, tool config
2. `src/tescmd/__init__.py` — package version
3. `src/tescmd/__main__.py` — `python -m tescmd` entry point
4. `src/tescmd/models/config.py` — AppConfig, Profile (pydantic-settings)
5. `src/tescmd/models/auth.py` — TokenResponse, AuthConfig
6. `src/tescmd/models/vehicle.py` — Vehicle, VehicleData, DriveState, ChargeState, ClimateState, VehicleState, VehicleConfig, GuiSettings
7. `src/tescmd/models/command.py` — CommandResponse, CommandResult
8. `src/tescmd/models/__init__.py` — re-exports
9. `src/tescmd/config/settings.py` — Settings class (env + .env + TOML + defaults)
10. `src/tescmd/config/profiles.py` — Profile loading from config.toml
11. `src/tescmd/config/__init__.py`
12. `src/tescmd/output/json_output.py` — JSON envelope serialization
13. `src/tescmd/output/rich_output.py` — Rich tables, panels, status displays
14. `src/tescmd/output/formatter.py` — OutputFormatter (TTY auto-detect, dispatch)
15. `src/tescmd/output/__init__.py`
16. `src/tescmd/_internal/async_utils.py` — run_async helper
17. `src/tescmd/_internal/vin.py` — VIN resolution chain
18. `src/tescmd/_internal/__init__.py`
19. `tests/conftest.py` — shared fixtures
20. Tests: settings, models, output formatting

### Phase B: HTTP Client + Auth

21. `src/tescmd/api/errors.py` — AuthError, VehicleAsleepError, CommandFailedError, RateLimitError, NetworkError, ConfigError
22. `src/tescmd/api/client.py` — TeslaFleetClient (httpx async, auth, regions, retry)
23. `src/tescmd/api/__init__.py`
24. `src/tescmd/auth/server.py` — local OAuth callback server
25. `src/tescmd/auth/oauth.py` — PKCE flow (verifier, challenge, auth URL, code exchange)
26. `src/tescmd/auth/token_store.py` — keyring read/write/delete, metadata
27. `src/tescmd/auth/__init__.py`
28. `src/tescmd/cli/main.py` — root parser, global args, dispatch, asyncio.run
29. `src/tescmd/cli/auth.py` — login, logout, status, refresh, export, import
30. `src/tescmd/cli/__init__.py`
31. Tests: client with httpx mocks, auth flow

### Phase C: Vehicle Data + CLI

32. `src/tescmd/api/vehicle.py` — VehicleAPI (list, info, data, location, wake)
33. `src/tescmd/cli/vehicle.py` — vehicle subcommands (list, info, data, location, wake)
34. Tests: vehicle list, vehicle location with mocked responses
35. Manual smoke test: auth login → vehicle list → vehicle location

## File Manifest

```
pyproject.toml
src/tescmd/
├── __init__.py
├── __main__.py
├── cli/
│   ├── __init__.py
│   ├── main.py
│   ├── auth.py
│   └── vehicle.py
├── api/
│   ├── __init__.py
│   ├── client.py
│   ├── vehicle.py
│   └── errors.py
├── models/
│   ├── __init__.py
│   ├── vehicle.py
│   ├── auth.py
│   ├── command.py
│   └── config.py
├── auth/
│   ├── __init__.py
│   ├── oauth.py
│   ├── token_store.py
│   └── server.py
├── output/
│   ├── __init__.py
│   ├── formatter.py
│   ├── rich_output.py
│   └── json_output.py
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── profiles.py
└── _internal/
    ├── __init__.py
    ├── vin.py
    └── async_utils.py
tests/
├── conftest.py
├── test_settings.py
├── test_models.py
├── test_output.py
├── api/
│   └── test_client.py
├── auth/
│   └── test_oauth.py
└── cli/
    ├── test_auth.py
    └── test_vehicle.py
```

Total: 28 source files, 8 test files
