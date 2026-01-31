# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - Unreleased

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
- **E2E test script** — `scripts/e2e_test.py` provides interactive end-to-end command testing against a live vehicle with per-command confirmation, category filtering, and destructive-command skipping

## [0.1.0] - Unreleased

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
