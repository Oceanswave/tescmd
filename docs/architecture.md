# Architecture

## Overview

tescmd follows a layered architecture with strict separation of concerns. Each layer depends only on the layer below it.

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                     │
│  cli/main.py ─ cli/auth.py ─ cli/vehicle.py     │
│  cli/charge.py ─ cli/climate.py ─ cli/key.py    │
│  cli/security.py ─ cli/setup.py ─ cli/trunk.py  │
│        (Click groups, dispatch, output)          │
├─────────────────────────────────────────────────┤
│                   API Layer                      │
│  api/vehicle.py ─ api/command.py                 │
│  api/signed_command.py ─ api/energy.py           │
│  (domain methods, command routing, signing)      │
├─────────────────────────────────────────────────┤
│              Protocol Layer                      │
│  protocol/session.py ─ protocol/signer.py        │
│  protocol/encoder.py ─ protocol/metadata.py      │
│  protocol/commands.py ─ protocol/protobuf/       │
│  (ECDH sessions, HMAC signing, protobuf)         │
├─────────────────────────────────────────────────┤
│                  Client Layer                    │
│              api/client.py                       │
│   (HTTP transport, auth headers, base URLs)      │
├─────────────────────────────────────────────────┤
│                 Auth Layer                       │
│  auth/oauth.py ─ auth/token_store.py             │
│    (OAuth2 PKCE, token refresh, keyring)         │
├─────────────────────────────────────────────────┤
│              Telemetry Layer                      │
│  telemetry/server.py ─ telemetry/decoder.py      │
│  telemetry/dashboard.py ─ telemetry/fields.py    │
│  telemetry/tailscale.py ─ telemetry/flatbuf.py   │
│  (WebSocket server, protobuf decode, Rich TUI)   │
├─────────────────────────────────────────────────┤
│               Infrastructure                     │
│  output/ ─ crypto/ ─ models/ ─ _internal/        │
│  cache/ ─ deploy/ ─ (formatting, keys, schemas)  │
└─────────────────────────────────────────────────┘
```

## Data Flow

### Typical Data Query Execution

```
User runs: tescmd vehicle data

  1. cli/main.py
     ├── Click parses global args (--vin, --format, --profile)
     ├── Creates AppContext with settings
     └── Dispatches to cli/vehicle.py

  2. cli/vehicle.py
     ├── Click parses subcommand args
     ├── Resolves VIN (arg > flag > env > profile > picker)
     ├── Creates API client
     └── Calls api/vehicle.py → get_vehicle_data(vin)

  3. api/vehicle.py
     ├── Builds query parameters
     └── Calls client.get("/api/1/vehicles/{vin}/vehicle_data")

  4. api/client.py (TeslaFleetClient)
     ├── Injects Authorization header (from token store)
     ├── Selects regional base URL
     ├── Sends HTTP request via httpx
     ├── Handles 401 → triggers token refresh → retries
     └── Returns parsed response

  5. cli/vehicle.py (back in CLI layer)
     ├── Receives VehicleData model
     └── Passes to output/formatter.py for display

  6. output/formatter.py
     ├── TTY detected? → rich_output.py (Rich tables with unit conversion)
     ├── Piped? → json_output.py (JSON object)
     └── --quiet? → stderr summary only
```

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

Each file corresponds to a command group (`auth`, `vehicle`, `key`, `setup`). Built with **Click**. Responsibilities:

- Define Click command groups, commands, and options
- Resolve VIN and other context via `AppContext`
- Call API layer methods using `run_async()` helper
- Format and display output via `OutputFormatter`
- Handle user-facing errors (translate API errors to messages)

CLI modules do **not** construct HTTP requests or handle auth tokens directly.

**Currently implemented command groups:**
- `auth` — login (`--reconsent`), logout, status, refresh, register, export, import
- `vehicle` — list, info, data, location, wake, alerts, release-notes, service, drivers, telemetry (config, create, delete, errors, stream)
- `charge` — status, start, stop, limit, amps, schedule, departure, precondition
- `climate` — status, on, off, set, seat, keeper, cop-temp, auto-seat, auto-wheel, wheel-level
- `security` — status, lock, unlock, sentry, valet, remote-start, flash, honk, speed-limit, pin management
- `trunk` — open, close, frunk, window
- `media` — play-pause, next/prev track, next/prev fav, volume
- `nav` — send, gps, supercharger, homelink, waypoints
- `software` — status, schedule, cancel
- `energy` — list, status, live, backup, mode, storm, tou, history, off-grid, grid-config, calendar
- `user` — me, region, orders, features
- `sharing` — add/remove driver, create/redeem/revoke/list invites
- `key` — generate, deploy, validate, show, enroll, unenroll
- `cache` — status, clear
- `raw` — get, post
- `setup` — interactive first-run configuration wizard with key enrollment

### `api/` — API Client

- **`client.py`** (`TeslaFleetClient`) — Base HTTP client. Manages httpx session, auth headers, base URL, retries, token refresh.
- **`vehicle.py`** (`VehicleAPI`) — Vehicle data endpoints (list, info, data, location, wake, alerts, drivers).
- **`command.py`** (`CommandAPI`) — Vehicle command endpoints (~50 commands via POST).
- **`signed_command.py`** (`SignedCommandAPI`) — Vehicle Command Protocol wrapper. Routes signed commands through ECDH session + HMAC path; delegates unsigned commands to `CommandAPI`.
- **`energy.py`** (`EnergyAPI`) — Energy product endpoints (Powerwall, solar).
- **`sharing.py`** (`SharingAPI`) — Driver and invite management.
- **`user.py`** (`UserAPI`) — Account info, region, orders, features.
- **`errors.py`** — Typed exceptions: `AuthError`, `MissingScopesError`, `VehicleAsleepError`, `SessionError`, `KeyNotEnrolledError`, `TierError`, `RateLimitError`, `TunnelError`, `TailscaleError`, etc.

API classes use **composition**: they receive a `TeslaFleetClient` instance, not extend it.

```python
class VehicleAPI:
    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def list_vehicles(self) -> list[Vehicle]:
        resp = await self._client.get("/api/1/vehicles")
        return [Vehicle(**v) for v in resp["response"]]
```

### `models/` — Data Models

Pydantic v2 models for all structured data:

- **`vehicle.py`** — `Vehicle`, `VehicleData`, `DriveState`, `ChargeState`, `ClimateState`, `VehicleState`, `VehicleConfig`, `GuiSettings`
- **`auth.py`** — `TokenData`, `TokenMeta`, `AuthConfig`, `PARTNER_SCOPES`, `decode_jwt_scopes`
- **`command.py`** — `CommandResponse`, `CommandResult`
- **`config.py`** — `AppSettings` (pydantic-settings for env/file loading)

Models serve as the **contract** between layers. API methods return models; CLI methods accept and display models. All vehicle models use `extra="allow"` so unknown API fields are preserved without errors.

### `auth/` — Authentication

- **`oauth.py`** — OAuth2 PKCE flow implementation. Generates verifier/challenge, builds auth URL, handles code exchange. Also handles partner account registration with scope verification. Supports `--reconsent` via `prompt_missing_scopes=true` for re-granting expanded scopes.
- **`token_store.py`** — Wraps `keyring` for OS-native credential storage. Stores access token, refresh token, expiry, and metadata.
- **`server.py`** — Ephemeral local HTTP server that receives the OAuth redirect callback.

### `protocol/` — Vehicle Command Protocol

Implements Tesla's signed command protocol (ECDH + HMAC-SHA256):

- **`session.py`** (`SessionManager`) — Manages per-(VIN, domain) ECDH sessions with in-memory caching, counter management, and automatic re-handshake on expiry.
- **`signer.py`** — HMAC-SHA256 key derivation and command tag computation. VCSEC tags are truncated to 17 bytes.
- **`encoder.py`** — Builds `RoutableMessage` protobuf envelopes for session handshakes and signed commands. Handles base64 encoding for the API.
- **`metadata.py`** — TLV (tag-length-value) serialization for command metadata (epoch, expiry, counter, flags).
- **`commands.py`** — Command registry mapping REST command names to protocol domain + signing requirements.
- **`protobuf/messages.py`** — Hand-written protobuf dataclasses (`RoutableMessage`, `SessionInfo`, `Destination`, `SignatureData`, etc.) with `serialize()` and `parse()` methods.

See [vehicle-command-protocol.md](vehicle-command-protocol.md) for the full protocol specification.

### `crypto/` — Key Management and ECDH

- **`keys.py`** — EC P-256 key generation, PEM export/import, public key extraction.
- **`ecdh.py`** — ECDH key exchange (`derive_session_key`) and uncompressed public key extraction.
- **`schnorr.py`** — Schnorr signature implementation for telemetry server authentication handshake.

### `output/` — Output Formatting

- **`formatter.py`** — `OutputFormatter` detects output context (TTY, pipe, quiet flag) and delegates.
- **`rich_output.py`** — Rich-based rendering: tables for vehicle data, charge status, climate status, vehicle config, GUI settings. Includes `DisplayUnits` for configurable unit conversion (°F/°C, mi/km, PSI/bar).
- **`json_output.py`** — JSON serialization with consistent structure for machine parsing.

### `telemetry/` — Fleet Telemetry Streaming

- **`server.py`** (`TelemetryServer`) — Async WebSocket server that receives telemetry push from Tesla. Handles TLS via Tailscale Funnel certs, Schnorr-based authentication handshake, and frame dispatch.
- **`decoder.py`** (`TelemetryDecoder`) — Decodes protobuf-encoded telemetry payloads using official Tesla proto definitions (`vehicle_data`, `vehicle_alert`, `vehicle_error`, `vehicle_metric`, `vehicle_connectivity`). Returns typed `TelemetryFrame` dataclasses.
- **`flatbuf.py`** — FlatBuffer parser for Tesla's alternative telemetry encoding format.
- **`fields.py`** — Field name registry (120+ fields) with preset configs (`default`, `driving`, `charging`, `climate`, `all`). Maps field names to protobuf field numbers.
- **`dashboard.py`** (`TelemetryDashboard`) — Rich Live TUI with field name, value, and last-update columns. Supports unit conversion via `DisplayUnits`, connection status, frame counter, and uptime display.
- **`tailscale.py`** (`TailscaleManager`) — Subprocess-based Tailscale management: check installation, start/stop Funnel, retrieve TLS certs, serve files at specific paths.

**Optional dependency:** `pip install tescmd[telemetry]` adds `websockets>=14.0`.

### `deploy/` — Key Deployment

- **`github_pages.py`** — Deploys the public key to a GitHub Pages repo at the `.well-known` path.
- **`tailscale_serve.py`** — Hosts the public key via Tailscale Funnel at `https://<machine>.tailnet.ts.net/.well-known/appspecific/com.tesla.3p.public-key.pem`.

### `_internal/` — Shared Utilities

- **`vin.py`** — Smart VIN resolution: checks positional arg, `--vin` flag, active profile, then falls back to interactive vehicle picker.
- **`async_utils.py`** — `run_async()` helper for running async code from sync Click entry points.
- **`permissions.py`** — Cross-platform file permissions: `secure_file()` uses `chmod 0600` on Unix and `icacls` on Windows.

## Design Decisions

### Why Composition Over Inheritance

API classes (`VehicleAPI`) wrap a `TeslaFleetClient` instance rather than inheriting from it. This provides:

- **Testability** — inject a mock client
- **Separation** — domain logic doesn't leak into HTTP transport
- **Flexibility** — the client can be shared across API classes without diamond inheritance

### Why Click

- Natural fit for nested command groups (`tescmd auth login`, `tescmd vehicle data`)
- Decorator-based interface keeps commands concise
- Built-in support for `--help`, types, choices, environment variable fallbacks
- `@click.pass_obj` context propagation works well with `AppContext` pattern
- Async integration via `run_async()` wrapper

### Why REST-First with Portal Key Enrollment

Tesla's Fleet API handles all vehicle commands over REST. Key enrollment (registering a public key on the vehicle) is the only operation outside the REST API. The primary enrollment path uses the Tesla Developer Portal — a web-based flow where the vehicle receives the key over cellular and the owner confirms via the Tesla app. BLE enrollment is an alternative for offline provisioning.

### Why Transparent Command Signing

The `SignedCommandAPI` wraps `CommandAPI` using composition, not inheritance. `get_command_api()` returns whichever is appropriate based on available keys and the `command_protocol` setting. CLI command modules call methods by name on the returned API object and never need to know whether signing is active. This means:

- Zero code changes needed in CLI modules when signing is enabled
- `wake_up` and unknown commands pass through to unsigned REST automatically
- The `command_protocol` setting provides an escape hatch for debugging

### Why Auto-Detect Output Format

Scripts that pipe tescmd output need JSON. Humans at a terminal want Rich formatting. Auto-detection (`sys.stdout.isatty()`) serves both without requiring flags, while `--format` provides explicit override when needed.

### Why Display-Layer Unit Conversion

The Tesla API returns temperatures in Celsius, distances in miles, and tire pressures in bar. Rather than converting in the Pydantic models (which would lose the raw API values), conversions happen in `RichOutput` via the `DisplayUnits` dataclass. This means:

- JSON output always contains raw API values (consistent, machine-readable)
- Rich output displays human-friendly units (configurable)
- Models remain faithful mirrors of the API contract

### Why Keyring for Token Storage

OS-level credential storage (macOS Keychain, GNOME Keyring, Windows Credential Locker) is more secure than plaintext files. The `keyring` library provides a cross-platform interface with graceful fallback to file-based storage.

### Why python-dotenv

Keeps secrets (`TESLA_CLIENT_ID`, `TESLA_CLIENT_SECRET`) out of config files that might be committed. `.env` is gitignored by convention and loaded automatically at startup.
