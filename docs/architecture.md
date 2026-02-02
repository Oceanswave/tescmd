# Architecture

## Overview

tescmd follows a layered architecture with strict separation of concerns. Each layer depends only on the layer below it.

```
┌─────────────────────────────────────────────────┐
│                    CLI Layer                     │
│  cli/main.py ─ cli/auth.py ─ cli/vehicle.py     │
│  cli/charge.py ─ cli/climate.py ─ cli/key.py    │
│  cli/security.py ─ cli/setup.py ─ cli/trunk.py  │
│  cli/openclaw.py ─ cli/mcp_cmd.py ─ cli/serve.py │
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
│  telemetry/fanout.py ─ telemetry/mapper.py       │
│  telemetry/cache_sink.py                         │
│  (WebSocket server, protobuf decode, Rich TUI,   │
│   frame fan-out, cache warming, field mapping)    │
├─────────────────────────────────────────────────┤
│              OpenClaw Layer                       │
│  openclaw/config.py ─ openclaw/filters.py        │
│  openclaw/emitter.py ─ openclaw/gateway.py       │
│  openclaw/dispatcher.py ─ openclaw/bridge.py     │
│  openclaw/telemetry_store.py                     │
│  (filter, emit, gateway, command dispatch, store) │
├─────────────────────────────────────────────────┤
│              Triggers Layer                       │
│  triggers/models.py ─ triggers/manager.py        │
│  (condition models, evaluation engine, cooldown)  │
├─────────────────────────────────────────────────┤
│                 MCP Layer                        │
│  mcp/server.py                                   │
│  (FastMCP server, CliRunner + custom tool invoke) │
├─────────────────────────────────────────────────┤
│               Infrastructure                     │
│  output/ ─ crypto/ ─ models/ ─ _internal/        │
│  cache/ ─ deploy/ ─ (formatting, keys, schemas)  │
└─────────────────────────────────────────────────┘
```

## Data Flow

### First-Run Setup

```
User runs: tescmd setup

  Phase 0: Tier Selection
     └── Read-only (data only) or Full control (data + commands + telemetry)

  Phase 1: Domain Setup
     ├── Detects GitHub CLI → auto-creates GitHub Pages site
     └── Or: manual domain entry

  Phase 2: Developer Portal Walkthrough
     ├── Guides Tesla Developer app creation
     └── Persists Client ID / Client Secret to .env

  Phase 3: Key Generation & Deployment (full tier only)
     ├── Generates EC P-256 key pair (crypto/keys.py)
     └── Deploys public key to GitHub Pages or Tailscale Funnel

  Phase 3.5: Key Enrollment (full tier only)
     └── Opens enrollment URL → user approves in Tesla app

  Phase 4: Fleet API Partner Registration
     └── Calls partner registration endpoint (api/partner.py)

  Phase 5: OAuth Login
     ├── auth/oauth.py → PKCE flow → browser → callback
     └── auth/token_store.py → keyring storage

  Phase 6: Summary + next steps
```

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

The recommended entry point is `tescmd setup`, which handles domain provisioning, Developer Portal credentials, key generation, Fleet API registration, and OAuth login in one guided wizard (see First-Run Setup above). For standalone auth:

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
- `billing` — Supercharger billing history and invoices
- `cache` — status, clear
- `charge` — status, start, stop, limit, amps, schedule, departure, precondition
- `climate` — status, on, off, set, seat, keeper, cop-temp, auto-seat, auto-wheel, wheel-level
- `energy` — list, status, live, backup, mode, storm, tou, history, off-grid, grid-config, calendar
- `key` — generate, deploy, validate, show, enroll, unenroll
- `mcp` — serve (stdio + streamable-http transports, OAuth 2.1, Tailscale Funnel)
- `media` — play-pause, next/prev track, next/prev fav, volume
- `nav` — send, gps, supercharger, homelink, waypoints
- `openclaw` — bridge (filtered telemetry → OpenClaw Gateway, bidirectional command dispatch)
- `serve` — unified MCP + telemetry + OpenClaw TUI dashboard with trigger subscriptions
- `partner` — public-key lookup, account endpoints
- `raw` — get, post
- `security` — status, lock, unlock, sentry, valet, remote-start, flash, honk, speed-limit, pin management
- `setup` — interactive first-run configuration wizard (see First-Run Setup)
- `sharing` — add/remove driver, create/redeem/revoke/list invites
- `software` — status, schedule, cancel
- `status` — single-command overview of config, auth, and cache state
- `trunk` — open, close, frunk, window
- `user` — me, region, orders, features
- `vehicle` — list, info, data, location, wake, alerts, release-notes, service, drivers, telemetry (config, create, delete, errors, stream)

### `api/` — API Client

- **`client.py`** (`TeslaFleetClient`) — Base HTTP client. Manages httpx session, auth headers, base URL, retries, token refresh.
- **`vehicle.py`** (`VehicleAPI`) — Vehicle data endpoints (list, info, data, location, wake, alerts, drivers).
- **`command.py`** (`CommandAPI`) — Vehicle command endpoints (~50 commands via POST).
- **`signed_command.py`** (`SignedCommandAPI`) — Vehicle Command Protocol wrapper. Routes signed commands through ECDH session + HMAC path; delegates unsigned commands to `CommandAPI`.
- **`energy.py`** (`EnergyAPI`) — Energy product endpoints (Powerwall, solar).
- **`charging.py`** (`ChargingAPI`) — Supercharger billing and charging session endpoints.
- **`partner.py`** (`PartnerAPI`) — Partner account registration and public key lookup.
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
- **`setup.py`** (`telemetry_session()`) — Async context manager encapsulating the full telemetry lifecycle: server start → Tailscale tunnel → partner domain re-registration → fleet config → yield → cleanup. Shared by both `cli/vehicle.py` (stream) and `cli/openclaw.py` (bridge).
- **`tailscale.py`** (`TailscaleManager`) — Subprocess-based Tailscale management: check installation, start/stop Funnel, retrieve TLS certs, serve files at specific paths.
- **`fanout.py`** (`FrameFanout`) — Multiplexes a single `on_frame` callback to N sinks. Each sink is error-isolated; one failing sink does not affect others.
- **`mapper.py`** (`TelemetryMapper`) — Maps Fleet Telemetry field names (e.g. `Soc`, `Location`) to VehicleData JSON paths (e.g. `charge_state.usable_battery_level`). Includes type-safe transforms for each field.
- **`cache_sink.py`** (`CacheSink`) — Telemetry sink that warms the `ResponseCache` by translating incoming frames via `TelemetryMapper` and merging them into the disk cache. Buffered writes with configurable flush interval.

**Dependency:** `websockets>=14.0` (core dependency).

### `openclaw/` — OpenClaw Bridge

- **`config.py`** (`BridgeConfig`, `FieldFilter`) — Pydantic models for bridge configuration with per-field delta threshold and throttle interval settings. Loadable from JSON files with CLI override merging.
- **`filters.py`** (`DualGateFilter`) — Dual-gate emission filter: both delta threshold (value change) AND throttle interval (minimum time) must pass for a field to be emitted. Location fields use haversine distance; numeric fields use absolute difference; zero-granularity fields emit on any value change.
- **`emitter.py`** (`EventEmitter`) — Transforms telemetry field data into OpenClaw `req:agent` event payloads. Maps telemetry fields to event types (location, battery, temperature, speed, charge state transitions, security changes).
- **`gateway.py`** (`GatewayClient`) — WebSocket client implementing the OpenClaw operator protocol (challenge → connect → hello-ok handshake) with Ed25519 device key signing. Includes exponential backoff reconnection (1s base → 60s max with up to 10% jitter per interval).
- **`dispatcher.py`** (`CommandDispatcher`) — Bidirectional command dispatch over the gateway. Routes inbound `node.invoke.request` messages to read handlers (in-memory telemetry store), write handlers (Fleet API with tier + VCSEC guards), trigger handlers, and `system.run` meta-dispatch with API-style alias mapping.
- **`telemetry_store.py`** (`TelemetryStore`) — In-memory latest-value cache for telemetry fields. Populated by `TelemetryBridge.on_frame()`, queried by dispatcher read handlers (e.g. `location.get`, `battery.get`).
- **`bridge.py`** (`TelemetryBridge`, `build_openclaw_pipeline()`) — Orchestrator wiring: `TelemetryServer.on_frame` → telemetry store update → trigger evaluation → `DualGateFilter` → `EventEmitter` → `GatewayClient`. Factory function `build_openclaw_pipeline()` constructs the full pipeline. Supports dry-run mode (JSONL to stdout).

**Dependency:** `websockets>=14.0` (core dependency, shared with telemetry layer).

### `triggers/` — Trigger Subscription System

- **`models.py`** (`TriggerOperator`, `TriggerCondition`, `TriggerDefinition`, `TriggerNotification`) — Pydantic v2 models for trigger conditions (9 operators: lt, gt, lte, gte, eq, neq, changed, enter, leave), definitions (one-shot vs persistent with cooldown), and notification payloads. Model validators enforce operator-specific value requirements (geofence needs lat/lon/radius dict, changed needs no value).
- **`manager.py`** (`TriggerManager`) — Evaluation engine with field-indexed lookup, cooldown tracking, dual-channel notification delivery (pending deque for MCP polling + async callbacks for OpenClaw push), and one-shot auto-deletion. Geofence operators use haversine distance for boundary-crossing detection. Limits: 100 triggers, 500 pending notifications.

### `mcp/` — MCP Server

- **`server.py`** (`MCPServer`, `_InMemoryOAuthProvider`, `_PermissiveClient`) — Registers all tescmd CLI commands as MCP tools using Click's `CliRunner` for invocation (with `env=os.environ.copy()` to propagate auth tokens). Guarantees behavioral parity with the CLI (caching, wake, auth all work). Read tools annotated with `readOnlyHint: true`; write tools with `readOnlyHint: false`. Supports stdio and streamable-http transports via FastMCP. Custom tool registry (`register_custom_tool()`) enables runtime-registered non-CLI tools (used by trigger system).

  **OAuth 2.1:** The HTTP transport implements the full MCP OAuth 2.1 specification via `_InMemoryOAuthProvider`. Clients authenticate through an authorization code flow with PKCE — the server auto-approves and returns tokens. `_PermissiveClient` wraps `OAuthClientInformationFull` to accept any redirect URI and scope, supporting clients that skip dynamic registration (e.g. Claude.ai). DNS rebinding protection via `TransportSecuritySettings` allows Tailscale Funnel hostnames alongside localhost.

**Dependency:** `mcp>=1.0` (core dependency).

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

### Why a Unified Serve Pipeline

`tescmd serve` consolidates MCP server, telemetry streaming, cache warming, and OpenClaw bridging into a single command. The key abstraction is `FrameFanout` — a multiplexer that delivers each telemetry frame to N sinks independently:

```
Tesla Vehicle (Fleet Telemetry push)
    → TelemetryServer (WebSocket, exposed via Tailscale Funnel)
        → TelemetryDecoder (protobuf → TelemetryFrame)
            → FrameFanout.on_frame()
                ├→ CacheSink (warms ResponseCache from telemetry)
                ├→ TelemetryDashboard (Textual TUI, TTY only)
                ├→ JSONL stdout sink (piped/JSON mode)
                ├→ TriggerManager.evaluate() (when no OpenClaw)
                └→ TelemetryBridge → OpenClaw Gateway (optional)
                     └→ includes trigger evaluation internally
    ┊
    └→ MCP Server (HTTP or stdio, reads from warmed cache)
```

Each sink is error-isolated: one failing sink does not affect others. The `CacheSink` translates telemetry field names to VehicleData paths via `TelemetryMapper`, merging updates into the `ResponseCache` so MCP tool reads are free while telemetry is active.

Mode selection:
- **Default** (`serve VIN`): MCP + telemetry + cache warming + dashboard (TTY) or JSONL (piped)
- **MCP-only** (`serve --no-telemetry`): Lightweight MCP server, no telemetry
- **Telemetry-only** (`serve VIN --no-mcp`): Dashboard/JSONL without MCP
- **Combined** (`serve VIN --openclaw ws://...`): All of the above + OpenClaw bridge

### Why python-dotenv

Keeps secrets (`TESLA_CLIENT_ID`, `TESLA_CLIENT_SECRET`) out of config files that might be committed. `.env` is gitignored by convention and loaded automatically at startup.
