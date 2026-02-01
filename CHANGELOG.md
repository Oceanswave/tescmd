# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- **Optional dependency group** — `pip install tescmd[telemetry]` adds `websockets>=14.0`
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
