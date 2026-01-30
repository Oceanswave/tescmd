# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
