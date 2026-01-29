# Architecture

## Overview

tescmd follows a layered architecture with strict separation of concerns. Each layer depends only on the layer below it.

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                     │
│  cli/main.py ─ cli/charge.py ─ cli/vehicle.py   │
│         (argparse, dispatch, output)             │
├─────────────────────────────────────────────────┤
│                   API Layer                      │
│  api/vehicle.py ─ api/command.py ─ api/fleet.py  │
│       (domain methods, request building)         │
├─────────────────────────────────────────────────┤
│                  Client Layer                    │
│              api/client.py                       │
│   (HTTP transport, auth headers, base URLs)      │
├─────────────────────────────────────────────────┤
│                 Auth Layer                       │
│  auth/oauth.py ─ auth/token_store.py             │
│    (OAuth2 PKCE, token refresh, keyring)         │
├─────────────────────────────────────────────────┤
│               Infrastructure                     │
│  config/ ─ output/ ─ crypto/ ─ ble/ ─ models/   │
│  (settings, formatting, keys, BLE, schemas)      │
└─────────────────────────────────────────────────┘
```

## Data Flow

### Typical Command Execution

```
User runs: tescmd charge start

  1. cli/main.py
     ├── Parses global args (--vin, --format, --profile)
     ├── Loads settings (CLI > env > config > defaults)
     └── Dispatches to cli/charge.py

  2. cli/charge.py
     ├── Parses subcommand args
     ├── Resolves VIN (arg > flag > profile > picker)
     ├── Creates API client
     └── Calls api/command.py → start_charge(vin)

  3. api/command.py
     ├── Builds request payload
     └── Calls client.post("/api/1/vehicles/{id}/command/charge_start")

  4. api/client.py (TeslaFleetClient)
     ├── Injects Authorization header (from token store)
     ├── Selects regional base URL
     ├── Sends HTTP request via httpx
     ├── Handles 401 → triggers token refresh → retries
     └── Returns parsed response

  5. cli/charge.py (back in CLI layer)
     ├── Receives CommandResponse model
     └── Passes to output/formatter.py for display

  6. output/formatter.py
     ├── TTY detected? → rich_output.py (Rich panel)
     ├── Piped? → json_output.py (JSON object)
     └── --quiet? → stderr summary only
```

### Data Query Execution

```
User runs: tescmd charge status

  1. cli/main.py
     ├── Parses global args (--vin, --format, --profile)
     ├── Loads settings (CLI > env > config > defaults)
     └── Dispatches to cli/charge.py

  2. cli/charge.py
     ├── Parses subcommand args (status)
     ├── Resolves VIN (arg > flag > profile > picker)
     ├── Creates API client
     └── Calls api/vehicle.py → get_vehicle_data(vin, endpoints=["charge_state"])

  3. api/vehicle.py
     ├── Builds query parameters
     └── Calls client.get("/api/1/vehicles/{vin}/vehicle_data?endpoints=charge_state")

  4. api/client.py (TeslaFleetClient)
     ├── Injects Authorization header (from token store)
     ├── Sends HTTP GET via httpx
     └── Returns parsed response as ChargeState model

  5. cli/charge.py (back in CLI layer)
     ├── Receives ChargeState model
     └── Passes to output/formatter.py for display

  6. output/formatter.py
     ├── TTY? → rich_output.py (Rich panel: battery %, range, rate, etc.)
     ├── Piped? → json_output.py (JSON with charge_state fields)
     └── --quiet? → stderr summary only
```

Note: Data queries (status, info, location, data) go through `VehicleAPI` and only require an OAuth token. Commands (start, stop, lock, etc.) go through `CommandAPI` and may require an enrolled EC key.

### Authentication Flow

```
User runs: tescmd auth login

  1. cli/auth.py
     ├── Reads client_id / client_secret from settings
     └── Calls auth/oauth.py → start_auth_flow()

  2. auth/oauth.py
     ├── Generates PKCE code_verifier + code_challenge
     ├── Builds authorization URL with scopes
     ├── Starts local callback server (auth/server.py)
     ├── Opens system browser to Tesla auth page
     ├── Waits for OAuth redirect with auth code
     ├── Exchanges code for access_token + refresh_token
     └── Stores tokens via auth/token_store.py → keyring

  3. auth/token_store.py
     ├── Writes tokens to OS keyring (macOS Keychain, etc.)
     └── Stores metadata (expiry, scopes, region)
```

## Module Responsibilities

### `cli/` — Command-Line Interface

Each file corresponds to a command group (`auth`, `vehicle`, `charge`, etc.). Responsibilities:

- Define argparse subparsers and arguments
- Resolve VIN and other context
- Call API layer methods
- Format and display output
- Handle user-facing errors (translate API errors to messages)

CLI modules do **not** construct HTTP requests or handle auth tokens directly.

### `api/` — API Client

- **`client.py`** (`TeslaFleetClient`) — Base HTTP client. Manages httpx session, auth headers, base URL, retries, token refresh.
- **`vehicle.py`** (`VehicleAPI`) — Vehicle data endpoints (list, info, data).
- **`command.py`** (`CommandAPI`) — Vehicle command endpoints (charge, climate, security, etc.).
- **`fleet.py`** (`FleetAPI`) — Fleet-wide endpoints (status, telemetry config).
- **`errors.py`** — Typed exceptions: `AuthError`, `VehicleAsleepError`, `CommandFailedError`, `RateLimitError`, etc.

API classes use **composition**: they receive a `TeslaFleetClient` instance, not extend it.

```python
class CommandAPI:
    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def start_charge(self, vin: str) -> CommandResponse:
        return await self._client.post(f"/api/1/vehicles/{vin}/command/charge_start")
```

### `models/` — Data Models

Pydantic v2 models for all structured data:

- **`vehicle.py`** — `Vehicle`, `VehicleData`, `DriveState`, `ChargeState`, `ClimateState`, etc.
- **`auth.py`** — `TokenResponse`, `AuthConfig`
- **`command.py`** — `CommandResponse`, `CommandResult`
- **`config.py`** — `AppConfig`, `Profile` (pydantic-settings for env/file loading)

Models serve as the **contract** between layers. API methods return models; CLI methods accept and display models.

### `auth/` — Authentication

- **`oauth.py`** — OAuth2 PKCE flow implementation. Generates verifier/challenge, builds auth URL, handles code exchange.
- **`token_store.py`** — Wraps `keyring` for OS-native credential storage. Stores access token, refresh token, expiry, and metadata.
- **`server.py`** — Ephemeral local HTTP server that receives the OAuth redirect callback.

### `crypto/` — Key Management

- **`keys.py`** — EC P-256 key generation, PEM export/import, public key extraction.
- **`signing.py`** — Command signing for Tesla's vehicle command protocol (protocol v2).

### `output/` — Output Formatting

- **`formatter.py`** — `OutputFormatter` detects output context (TTY, pipe, quiet flag) and delegates.
- **`rich_output.py`** — Rich-based rendering: tables for lists, panels for details, spinners for async ops.
- **`json_output.py`** — JSON serialization with consistent structure for machine parsing.

### `config/` — Configuration

- **`settings.py`** — Pydantic Settings subclass. Merges CLI args, env vars (with `.env`), config.toml, and defaults.
- **`profiles.py`** — Named profiles in `config.toml`. Each profile stores VIN, region, output format preferences.

### `ble/` — Bluetooth Low Energy

- **`enroll.py`** — Uses `bleak` to communicate with the vehicle over BLE for key enrollment. This is the only module that requires physical proximity to the vehicle.

### `_internal/` — Shared Utilities

- **`vin.py`** — Smart VIN resolution: checks positional arg, `--vin` flag, active profile, then falls back to interactive vehicle picker.
- **`async_utils.py`** — Helpers for running async code from sync entry points, async timeouts, etc.

## Design Decisions

### Why Composition Over Inheritance

API classes (`VehicleAPI`, `CommandAPI`, `FleetAPI`) wrap a `TeslaFleetClient` instance rather than inheriting from it. This provides:

- **Testability** — inject a mock client
- **Separation** — domain logic doesn't leak into HTTP transport
- **Flexibility** — the client can be shared across API classes without diamond inheritance

### Why argparse Over click/typer

- Zero additional dependencies (stdlib)
- Works naturally with async (no decorator-based dispatch to fight)
- Full control over help formatting and error messages
- Nested subparsers (`tescmd charge start`) map cleanly to `cli/` file structure

### Why REST-First with Portal Key Enrollment

Tesla's Fleet API handles all vehicle commands over REST. Key enrollment (registering a public key on the vehicle) is the only operation outside the REST API. The primary enrollment path uses the Tesla Developer Portal — a web-based flow where the vehicle receives the key over cellular and the owner confirms via the Tesla app. BLE enrollment is an alternative for offline provisioning. Both paths are isolated to their own modules (`ble/enroll.py` is optional).

### Why Auto-Detect Output Format

Scripts that pipe tescmd output need JSON. Humans at a terminal want Rich formatting. Auto-detection (`sys.stdout.isatty()`) serves both without requiring flags, while `--format` provides explicit override when needed.

### Why Keyring for Token Storage

OS-level credential storage (macOS Keychain, GNOME Keyring, Windows Credential Locker) is more secure than plaintext files. The `keyring` library provides a cross-platform interface with graceful fallback to file-based storage.

### Why python-dotenv

Keeps secrets (`TESLA_CLIENT_ID`, `TESLA_CLIENT_SECRET`) out of config files that might be committed. `.env` is gitignored by convention and loaded automatically at startup.
