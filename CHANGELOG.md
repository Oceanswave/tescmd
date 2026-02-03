# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.3] - 2026-02-02

### Added

- **Unique app name generation** — setup wizard generates a `tescmd-<hex>` application name to prevent collisions on the Tesla Developer Portal; reused on re-runs unless `--force` is passed
- **In-process KeyServer** — ephemeral HTTP server (`KeyServer`) serves the PEM public key on localhost during interactive setup so Tailscale Funnel can proxy it without writing to the serve directory
- **Key mismatch warning** — setup wizard detects when the remote public key (GitHub Pages or Tailscale) differs from the local key and warns before Phase 2, so the user knows a redeploy is coming
- **`fetch_tailscale_key_pem()`** — synchronous helper in the deploy module to fetch the raw PEM from a Tailscale Funnel URL, mirroring `github_pages.fetch_key_pem()`
- **`TailscaleManager.start_proxy()`** — reverse-proxy mode (`tailscale serve --bg http://127.0.0.1:<port>`) for forwarding to a local HTTP server, distinct from the static-file `start_serve()`

### Changed

- **Setup phase reorder** — phases now run: keys → Fleet API registration → OAuth login → key enrollment (was: keys → enrollment → registration → OAuth); registration happens while credentials are fresh, enrollment is last so the user finishes in the Tesla app
- **Credentials always required** — both Client ID and Client Secret are mandatory with retry loops (3 attempts each); empty input no longer silently skips setup
- **Auto-save credentials** — `.env` file is written automatically after credential entry; removed the "Save to .env?" prompt
- **`--force` regenerates app name** — passing `--force` to setup now generates a fresh `tescmd-<hex>` name instead of reusing the saved one
- **Atomic Tailscale serve + Funnel** — `start_key_serving()` uses a single `tailscale serve --bg --funnel --set-path / <dir>` command instead of separate serve + funnel calls
- **`TailscaleManager.start_serve()` API** — added `port` and `funnel` keyword arguments for configurable HTTPS port and inline Funnel enablement
- **Enrollment messaging** — streamlined to focus on QR code scanning; removed duplicate URL display and the "Open in browser?" prompt (browser opens automatically)
- **GitHub Pages note** — clarified that Tailscale is used alongside GitHub Pages for telemetry streaming, not as a replacement
- **Funnel cleanup uses `stop_funnel()`** — finally block in `_interactive_setup` now calls the proper `TailscaleManager.stop_funnel()` method instead of the low-level `_run()` static method, preserving state tracking and idempotency

### Fixed

- **CLI module HTTP isolation** — moved direct `httpx.get()` call out of `setup.py` into `tailscale_serve.fetch_tailscale_key_pem()` to comply with single-responsibility layering (CLI handles args + output, deploy modules handle HTTP)

## [0.3.2] - 2026-02-02

### Fixed

- **OAuth URL printed for manual fallback** — `login_flow()` now prints the authorization URL before opening the browser so users can copy-paste it when `webbrowser.open()` fails
- **422 "already registered" treated as success** — `register_partner_account()` now treats HTTP 422 with "already been taken" as idempotent success instead of raising `AuthError`; re-running setup or `auth register` shows "Already registered — no action needed"
- **GitHub key comparison on re-deploy** — `_deploy_key_github()` fetches the remote public key and compares it to the local key; if they match, deployment is skipped; if they differ, the user is prompted before overwriting

## [0.3.1] - 2026-02-02

### Added

- **README overhaul** — header banner, logo, new "What It Does" summary section, expanded Prerequisites table with Python 3.11+, pip, Tesla account, and helpful links
- **Tailscale Funnel auto-detection in auth setup** — `_interactive_setup` now detects Tailscale and offers to start Funnel so Tesla can verify the origin URL during Developer Portal configuration; cleans up Funnel on exit
- **Tailscale hostname passthrough** — setup wizard forwards detected Tailscale hostname to auth flow, showing a concrete "Also add" origin URL instead of the generic placeholder
- **Comprehensive agent skill documentation** — expanded skill covering all command groups, triggers, and OpenClaw dispatch

### Fixed

- **Cross-platform file permissions** — OpenClaw gateway key file now uses `secure_file()` from `_internal.permissions` instead of raw `chmod(0o600)`, adding proper Windows support via `icacls`
- **12-factor app compliance** — config, disposability, and concurrency improvements across the codebase
- **Documentation accuracy** — corrected `media_adjust_volume` tool name in MCP docs; emphasized MCP/OpenClaw over direct CLI for cost savings in agent skill

## [0.3.0] - 2026-02-01

### Added

- **Unified `tescmd serve`** — single command combining MCP server, Fleet Telemetry streaming, cache warming, and optional OpenClaw bridge; full-screen TUI dashboard shows live telemetry, MCP status, tunnel URL, sink count, and connection health
- **TUI dashboard** — 8-panel Textual layout with telemetry field table, server info sidebar, activity log, request log, and filter status; command palette (`ctrl+p`), keybindings (`q` to quit, `f` to toggle filters), clean graceful shutdown
- **OpenClaw Bridge** — `tescmd openclaw bridge [VIN]` streams Fleet Telemetry to an OpenClaw Gateway with configurable delta+throttle filtering per field; supports `--dry-run` for JSONL output without a gateway connection
- **OpenClaw node role** — bidirectional command dispatch over the gateway WebSocket; bots send commands via the gateway that are forwarded as `node.invoke.request` events, routed through `CommandDispatcher` with read/write separation, tier enforcement, and VCSEC signing guards
- **Trigger subscription system** — `trigger.create`, `trigger.delete`, `trigger.list`, `trigger.poll` commands let bots register conditions on any telemetry field; supports operators `lt`, `gt`, `lte`, `gte`, `eq`, `neq`, `changed`, `enter`, `leave`; one-shot and persistent modes with configurable cooldown; max 100 triggers, 500 pending notifications
- **Geofence triggers** — `enter`/`leave` operators on Location field detect boundary crossings using haversine distance; fires only on actual crossing (not "already inside"), requires previous position for comparison
- **Trigger convenience aliases** — `cabin_temp.trigger`, `outside_temp.trigger`, `battery.trigger`, `location.trigger` pre-fill the field name so bots don't need to know raw telemetry field names
- **Trigger notification delivery** — dual-channel: OpenClaw push events (`trigger.fired`) for connected bots, and MCP polling via `trigger_poll` tool for agent frameworks
- **`system.run` meta-dispatch** — allows bots to invoke any registered handler by name with alias mapping (e.g., `door_lock` → `door.lock`, `auto_conditioning_start` → `climate.on`); guards against recursive self-dispatch
- **MCP Server** — `tescmd mcp serve` exposes all tescmd commands as MCP tools for Claude Desktop/Code and other agent frameworks; supports stdio and streamable-http transports with OAuth 2.1 authentication
- **MCP custom tool registry** — `MCPServer.register_custom_tool()` allows runtime registration of non-CLI tools (used by trigger system); custom tools appear alongside CLI-backed tools with proper schemas
- **Agent skill** — `skills/tescmd/SKILL.md` teaches AI agents how to use every tescmd command group with examples, parameter types, and common patterns
- **Reusable telemetry session** — extracted shared telemetry lifecycle (server → tunnel → partner registration → fleet config → cleanup) into `telemetry/setup.py` for use by serve, stream, and bridge commands
- **Dual-gate telemetry filter** — `openclaw/filters.py` combines delta threshold (value change) and throttle interval (minimum time between emissions) to reduce noise in telemetry streams; includes haversine distance for location fields
- **OpenClaw event emitter** — maps telemetry fields to OpenClaw `req:agent` event payloads (location, battery, temperature, speed, charge state transitions, security changes)
- **Gateway WebSocket client** — implements the OpenClaw operator protocol (challenge → connect → hello-ok handshake) with Ed25519 device key signing and exponential backoff reconnection
- **Bridge configuration** — `BridgeConfig` pydantic model with per-field filter settings, loadable from JSON file or CLI flags
- **CSV telemetry logging** — wide-format CSV log with one row per frame and one column per subscribed field; written to `~/.config/tescmd/logs/` by default, disable with `--no-log`
- **Cache sink** — telemetry-driven cache warming keeps read-command cache fresh while telemetry is active, making agent reads free
- **Frame fanout** — `FrameFanout` distributes decoded telemetry frames to multiple sinks (dashboard, CSV, cache, OpenClaw bridge, triggers) in parallel
- **Telemetry field mapper** — `telemetry/mapper.py` maps protobuf field names to tescmd model field names with unit conversion
- **Command guards in dispatcher** — extracted `check_command_guards()` (tier check + VCSEC signing requirement) into a shared function called by both CLI and OpenClaw dispatcher paths
- **Standard dependencies** — `websockets>=14.0`, `mcp>=1.0`, and `textual>=1.0` now included in default install

### Changed

- Refactored `_cmd_telemetry_stream` in `cli/vehicle.py` to use the shared `telemetry_session()` context manager (no behavioral change)
- Proto-aligned telemetry field definitions with proper `interval_seconds` for delta fields
- Separated JSON serialization errors from WebSocket connection errors in gateway send path for clearer diagnostics
- Raised trigger push notification and lifecycle event failures from debug to warning level for observability

### Fixed

- Fixed prompt for re-authentication when refresh token is expired or revoked (was failing silently)
- Fixed delta fields requiring `interval_seconds` configuration
- Fixed log file paths not shown on quit
- Added `exc_info` to MCP custom tool error logging for full stack traces
- Added JSON parse guards and explicit parameter validation in MCP tool wrappers
- Added `system.run` recursive self-dispatch guard

## [0.2.0] - 2026-01-31

### Added

- **Fleet Telemetry Streaming** — `tescmd vehicle telemetry stream [VIN]` starts a local WebSocket server, exposes it via Tailscale Funnel, configures the vehicle to push real-time telemetry, and displays it in an interactive Rich Live dashboard (TTY) or JSONL stream (piped)
- **Telemetry dashboard** — Rich Live TUI with field name, value, and last-update columns; unit conversion (°F/°C, mi/km, psi/bar); connection status; frame counter; uptime display
- **Protobuf telemetry decoder** — official Tesla protobuf definitions (`vehicle_data`, `vehicle_alert`, `vehicle_error`, `vehicle_metric`, `vehicle_connectivity`) for fully typed telemetry message parsing
- **FlatBuffer telemetry support** — `flatbuf.py` parser for Tesla's FlatBuffer-encoded telemetry payloads alongside protobuf
- **Field presets** — `--fields` option accepts preset names (`default`, `driving`, `charging`, `climate`, `all`) or comma-separated field names with 120+ registered telemetry fields
- **Interval override** — `--interval` option overrides the polling interval for all fields
- **Tailscale Funnel integration** — automatic Funnel start/stop with cert retrieval for Fleet Telemetry HTTPS requirement
- **JSONL output** — piped mode emits one JSON line per telemetry frame for scripting and log ingestion
- **TunnelError hierarchy** — `TunnelError` parent with `TailscaleError` subtype; actionable install/setup guidance
- **websockets dependency** — `websockets>=14.0` now included in default install
- **Tailscale key hosting** — `tescmd key deploy --method tailscale` hosts the public key via Tailscale Funnel at `https://<machine>.tailnet.ts.net/.well-known/appspecific/com.tesla.3p.public-key.pem`; auto-detected as second priority after GitHub Pages
- **Key hosting priority chain** — setup wizard and `key deploy` auto-detect the best hosting method: GitHub Pages → Tailscale Funnel → manual; `--method` flag overrides auto-detection
- **`TESLA_HOSTING_METHOD` setting** — persists the chosen key hosting method (`github`, `tailscale`) across sessions
- **Schnorr signature support** — `crypto/schnorr.py` for Schnorr-based authentication challenges used in telemetry server handshake
- **`auth import` command** — `tescmd auth import < tokens.json` imports tokens from a JSON file for headless/CI environments
- **Setup guide** — `docs/setup.md` with step-by-step walkthrough of all 7 setup phases
- **FAQ** — `docs/faq.md` covering common questions about tescmd, costs, hosting, and configuration
- **CI/CD workflows** — GitHub Actions for test-on-push (Python 3.11–3.13) and publish-to-PyPI-on-release via trusted publishing
- **README badges** — PyPI version, Python versions, CI build status, license, and GitHub release badges
- **E2E smoke tests** — `tests/cli/test_e2e_smoke.py` provides 179 pytest-based end-to-end tests covering every CLI command against the live Fleet API, with JSON envelope validation and save/restore for write commands (`pytest -m e2e`)

### Fixed

- Fixed telemetry dashboard uptime counter not incrementing
- Improved tunnel start/stop success messages for clarity

## [0.1.2] - 2025-01-31

### Added

- **Universal read-command caching** — every read command is now transparently cached with tiered TTLs (STATIC 1h, SLOW 5m, DEFAULT 1m, FAST 30s); bots can call tescmd as often as needed — within the TTL window, responses are instant and free
- **Generic cache key scheme** — `generic_cache_key(scope, identifier, endpoint, params)` generates scope-aware keys (`vin`, `site`, `account`, `partner`) for any API endpoint
- **`cached_api_call()` helper** — unified async helper that handles cache lookup, fetch, serialisation (Pydantic/dict/list/scalar), and storage for all non-vehicle-state read commands
- **Site-scoped cache invalidation** — `invalidate_cache_for_site()` clears energy site entries after write commands; `invalidate_cache_for_vin()` now also clears generic vin-scoped keys
- **`cache clear` options** — `--site SITE_ID` and `--scope {account,partner}` flags for targeted cache clearing alongside existing `--vin`
- **Partner endpoints** — `partner public-key`, `partner telemetry-error-vins`, `partner telemetry-errors` for partner account data (require client credentials)
- **Billing endpoints** — `billing history`, `billing sessions`, `billing invoice` for Supercharger charging data
- **Cross-platform file permissions** — `_internal/permissions.py` provides `secure_file()` using `chmod 0600` on Unix and `icacls` on Windows
- **Token store file backend** — `_FileBackend` with atomic writes and restricted permissions as fallback when keyring is unavailable
- **Spec-driven Fleet API validation** — `scripts/validate_fleet_api.py` validates implementation against `spec/fleet_api_spec.json` using AST introspection
- **6 missing Fleet API commands** — added `managed_charging_set_amps`, `managed_charging_set_location`, `managed_charging_set_schedule`, `add_charge_schedule`, `remove_charge_schedule`, `clear_charge_schedules`
- **Configurable display units** — `--units metric` flag switches all display values to °C/km/bar; individual env vars (`TESLA_TEMP_UNIT`, `TESLA_DISTANCE_UNIT`, `TESLA_PRESSURE_UNIT`) for granular control

### Fixed

- Aligned schedule/departure command parameters with Tesla Go SDK (correct param names and types)
- Fixed energy endpoint paths to match Fleet API spec
- Fixed Rich markup escaping bug in command output
- Aligned command parameters (3 param gaps) with Go SDK specs

### Changed

- Response cache documentation in CLAUDE.md expanded to cover universal caching, TTL tiers, and generic cache key scheme

## [0.1.1]

### Added

- **`status` command** — `tescmd status` shows current configuration, auth, cache, and key status at a glance
- **Retry option in wake prompt** — when a vehicle is asleep, the interactive prompt now offers `[R] Retry` alongside `[W] Wake via API` and `[C] Cancel`, allowing users to wake the vehicle for free via the Tesla app and retry without restarting the command
- **Key enrollment** — `tescmd key enroll <VIN>` sends the public key to the vehicle and guides the user through Tesla app approval with interactive [C]heck/[R]esend/[Q]uit prompt, `--wait` auto-polling, and JSON mode support
- **Tier enforcement** — readonly tier now blocks write commands with a clear error and upgrade guidance (`tescmd setup`)
- **Vehicle Command Protocol** — ECDH session management, HMAC-SHA256 command signing, and protobuf RoutableMessage encoding for the `signed_command` endpoint; commands are automatically signed when keys are available (`command_protocol=auto`)
- **SignedCommandAPI** — composition wrapper that transparently routes signed commands through the Vehicle Command Protocol while falling back to unsigned REST for `wake_up` and unknown commands
- **`command_protocol` setting** — `auto` (default), `signed`, or `unsigned` to control command routing; configurable via `TESLA_COMMAND_PROTOCOL` env var
- **Enrollment step in setup wizard** — full-tier setup now offers to enroll the key on a vehicle after key generation
- **Friendly command output** — all vehicle commands now display descriptive success messages (e.g. "Climate control turned on.", "Doors locked.") instead of bare "OK"
- **E2E smoke tests** — `tests/cli/test_e2e_smoke.py` provides 179 pytest-based end-to-end tests covering every CLI command against the live Fleet API, with JSON envelope validation and save/restore for write commands (`pytest -m e2e`)

## [0.1.0]

### Added

- OAuth2 PKCE authentication with browser-based login flow
- Vehicle state queries: battery, charge, climate, drive, location, doors, windows, trunks, tire pressure
- Vehicle commands: charge start/stop/limit/schedule, climate on/off/set/seats/wheel, lock/unlock, sentry, trunk/frunk, windows, media, navigation, software updates, HomeLink, speed limits, PIN management
- Energy products: Powerwall live status, site info, backup reserve, operation mode, storm mode, TOU settings, charging history, calendar history, grid config
- User account: profile info, region, orders, feature config
- Vehicle sharing: add/remove drivers, create/redeem/revoke invites
- Rich terminal output with tables, panels, and status indicators
- JSON output mode for scripting and agent integration
- Configurable display units (F/C, mi/km, PSI/bar)
- Response caching with configurable TTL for API cost reduction
- Cost-aware wake confirmation (interactive prompt or `--wake` flag)
- Multi-profile configuration support
- EC key generation and Tesla Developer Portal registration
- Raw API access (`raw get`, `raw post`) for uncovered endpoints
- First-run setup wizard with Fleet Telemetry cost guidance
