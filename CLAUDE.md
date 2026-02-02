# CLAUDE.md — Project Context for Claude Code

## Project Overview

**tescmd** is a Python 3.11+ CLI for querying and controlling Tesla vehicles via the [Tesla Fleet API](https://developer.tesla.com/docs/fleet-api). It covers auth, vehicle queries/commands, energy products, Supercharger billing, Fleet Telemetry streaming, OpenClaw bridge, and an MCP server for agent integration.

## Tech Stack

- **Python 3.11+**, **pydantic v2**, **click**, **httpx** (async), **rich**, **cryptography**, **protobuf**, **keyring**, **python-dotenv**
- **websockets** (telemetry + OpenClaw), **mcp** (MCP server) — core dependencies
- Optional: **bleak** (`[ble]` extra — BLE key enrollment)

## Project Structure

```
src/tescmd/
├── cli/                   # Click CLI layer
│   ├── main.py            # Root group, AppContext, _register_commands()
│   ├── _options.py        # Shared Click options/decorators (@global_options)
│   ├── _client.py         # API client builders, auto_wake, cached_vehicle_data, cached_api_call, TTL tiers
│   ├── auth.py, cache.py, charge.py, billing.py, climate.py, security.py
│   ├── status.py, trunk.py, vehicle.py, media.py, nav.py, partner.py
│   ├── software.py, energy.py, user.py, sharing.py, raw.py, key.py
│   ├── setup.py           # Interactive first-run wizard
│   ├── serve.py           # Unified MCP + telemetry + OpenClaw command
│   ├── openclaw.py        # Standalone openclaw bridge command
│   └── mcp_cmd.py         # mcp serve command
├── api/                   # HTTP client + domain APIs (composition pattern)
│   ├── client.py          # TeslaFleetClient (base HTTP, auth headers, retries)
│   ├── vehicle.py, command.py, signed_command.py, energy.py
│   ├── charging.py, partner.py, sharing.py, user.py
│   └── errors.py          # AuthError, VehicleAsleepError, TierError, TunnelError, etc.
├── models/                # Pydantic v2 models (vehicle, energy, user, auth, command, config)
├── auth/                  # OAuth2 PKCE, token_store (keyring + file fallback), callback server
├── protocol/              # Vehicle Command Protocol (ECDH sessions, HMAC signing, protobuf)
├── crypto/                # EC key gen, ECDH, Schnorr signatures
├── cache/                 # File-based JSON cache with tiered TTLs
├── output/                # OutputFormatter, RichOutput (DisplayUnits), JsonOutput
├── telemetry/             # Fleet Telemetry streaming
│   ├── setup.py           # Reusable telemetry_session() context manager
│   ├── server.py, decoder.py, fields.py, dashboard.py, tailscale.py
├── openclaw/              # OpenClaw bridge
│   ├── config.py          # BridgeConfig, FieldFilter, NodeCapabilities (pydantic)
│   ├── filters.py         # DualGateFilter (delta + throttle), haversine()
│   ├── emitter.py         # EventEmitter (telemetry → OpenClaw events)
│   ├── gateway.py         # GatewayClient (WebSocket, node protocol, Ed25519 auth)
│   ├── bridge.py          # TelemetryBridge orchestrator, build_openclaw_pipeline()
│   ├── dispatcher.py      # CommandDispatcher (reads, writes, triggers, system.run)
│   └── telemetry_store.py # In-memory latest-value cache for telemetry fields
├── triggers/              # Trigger subscription system
│   ├── models.py          # TriggerOperator, TriggerCondition, TriggerDefinition, TriggerNotification
│   └── manager.py         # TriggerManager (evaluation, cooldown, delivery, geofencing)
├── mcp/                   # MCP server
│   └── server.py          # MCPServer (FastMCP, CliRunner + custom callable tools)
├── deploy/                # Key hosting (GitHub Pages, Tailscale Funnel)
└── _internal/             # vin.py, async_utils.py, permissions.py
```

## Coding Conventions

- **Type hints everywhere** — all function signatures, all variables where non-obvious
- **async/await** — all API calls are async; CLI entry points use `run_async()` helper
- **Pydantic models** — all API request/response payloads; all configuration
- **src layout** — code in `src/tescmd/`, tests in `tests/`
- **No star imports** — explicit imports only
- **Single responsibility** — CLI modules handle args + output, API modules handle HTTP
- **Composition over inheritance** — API classes wrap `TeslaFleetClient`, don't extend it
- **Error stream routing** — JSON/piped mode writes errors to stderr; Rich/TTY mode uses stdout

## Key Patterns

**CLI command registration:** New command groups are registered in `cli/main.py:_register_commands()`. Each CLI module defines a Click group and is imported there.

**Global options propagation:** Use `@global_options` decorator from `cli/_options.py` on commands that need VIN, format, wake, cache flags. Options flow through `AppContext` via `@click.pass_obj`.

**API client construction:** `cli/_client.py` provides `get_vehicle_api(app_ctx)` → returns `(client, api)` tuple. Also `get_command_api()` for write commands (handles signed vs unsigned routing).

**Cache:** All read commands use `cached_api_call()` with scope-aware TTLs (STATIC 1h, SLOW 5m, DEFAULT 1m, FAST 30s). Write commands invalidate via `invalidate_cache_for_vin()` / `invalidate_cache_for_site()`.

**Output:** `OutputFormatter` auto-detects TTY → Rich, piped → JSON, `--quiet` → stderr only. JSON output uses a consistent `{ok, command, data, error, timestamp}` envelope.

**Telemetry session lifecycle:** `telemetry/setup.py:telemetry_session()` is an async context manager handling: server start → Tailscale tunnel → partner domain re-registration → fleet config → yield → cleanup. Used by both `cli/vehicle.py` (stream) and `cli/openclaw.py` (bridge).

**OpenClaw pipeline:** `TelemetryServer.on_frame` → `DualGateFilter.should_emit()` → `EventEmitter.to_event()` → `GatewayClient.send_event()`. The `TelemetryBridge` class wires these together. `build_openclaw_pipeline()` is the shared factory used by both `cli/openclaw.py` (standalone) and `cli/serve.py` (combined mode). Inbound commands flow: gateway `node.invoke.request` → `CommandDispatcher.dispatch()` → handler → `node.invoke.result`.

**Trigger system:** `TriggerManager` evaluates conditions on every telemetry frame (independent of the dual-gate filter). Supports numeric comparison (`lt`, `gt`, `eq`, etc.), `changed` detection, and geofence `enter`/`leave` with haversine distance. One-shot and persistent (with cooldown) firing modes. Notifications delivered via OpenClaw push and MCP polling (`trigger.poll`).

**MCP tools:** `mcp/server.py` maps tool names to CLI arg lists via `_CliToolDef` dataclasses. `invoke_tool()` uses `CliRunner.invoke(cli, ["--format", "json", "--wake", *args], env=os.environ.copy())`. Custom tools (e.g. trigger CRUD) use `_CustomToolDef` with direct callable handlers registered via `register_custom_tool()`. Read/write tools are separated for `readOnlyHint` annotations. HTTP transport uses OAuth 2.1 via `_InMemoryOAuthProvider` (auto-approve authorization, dynamic client registration, in-memory token storage) with `_PermissiveClient` wrappers that accept any redirect URI. DNS rebinding protection is configured to allow the Tailscale Funnel hostname when `public_url` is set.

## Build & Test

```bash
# Build
python -m build                    # hatchling via pyproject.toml

# Test (parallel by default via pytest-xdist)
pytest                             # all ~1600 tests
pytest tests/openclaw/ -x -v       # openclaw tests
pytest tests/triggers/ -x -v       # trigger tests
pytest tests/mcp/ -x -v            # mcp tests
pytest -m e2e                      # live API smoke tests (needs TESLA_ACCESS_TOKEN)

# Lint
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

## Environment Variables

| Variable | Description |
|---|---|
| `TESLA_CLIENT_ID` / `TESLA_CLIENT_SECRET` | OAuth2 app credentials |
| `TESLA_VIN` | Default vehicle VIN |
| `TESLA_REGION` | API region: `na`, `eu`, `cn` |
| `TESLA_ACCESS_TOKEN` / `TESLA_REFRESH_TOKEN` | Direct token override |
| `TESLA_TOKEN_FILE` | File path for token storage (skips keyring) |
| `TESLA_CONFIG_DIR` | Config directory (default: `~/.config/tescmd`) |
| `TESLA_CACHE_DIR` / `TESLA_CACHE_TTL` / `TESLA_CACHE_ENABLED` | Cache settings |
| `TESLA_OUTPUT_FORMAT` | Force format: `rich`, `json`, `quiet` |
| `TESLA_COMMAND_PROTOCOL` | `auto` (default), `signed`, `unsigned` |
| `TESLA_TEMP_UNIT` / `TESLA_DISTANCE_UNIT` / `TESLA_PRESSURE_UNIT` | Display units |
| `TESLA_DOMAIN` / `TESLA_HOSTING_METHOD` / `TESLA_GITHUB_REPO` | Key hosting |
| `TESLA_SETUP_TIER` | `readonly` or `full` |
| `TESLA_PROFILE` | Active config profile |
| `OPENCLAW_GATEWAY_TOKEN` | OpenClaw gateway auth token |
