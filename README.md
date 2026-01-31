# tescmd

<!-- [![PyPI](https://img.shields.io/pypi/v/tescmd)](https://pypi.org/project/tescmd/) -->
<!-- [![Python](https://img.shields.io/pypi/pyversions/tescmd)](https://pypi.org/project/tescmd/) -->
[![License](https://img.shields.io/github/license/oceanswave/tescmd)](LICENSE)

A Python CLI for querying and controlling Tesla vehicles via the Fleet API — built for both human operators and AI agents.

## Why tescmd?

Tesla's Fleet API gives developers full access to vehicle data and commands, but working with it directly means juggling OAuth2 PKCE flows, token refresh, regional endpoints, key enrollment, and raw JSON responses. tescmd wraps all of that into a single command-line tool that handles authentication, token management, and output formatting so you can focus on what you actually want to do — check your battery, find your car, or control your vehicle.

tescmd is designed to work as a tool that AI agents can invoke directly. Platforms like [OpenClaw](https://openclaw.ai/), [Claude Desktop](https://claude.ai), and other agent frameworks can call tescmd commands, parse the structured JSON output, and take actions on your behalf — "lock my car", "what's my battery at?", "start climate control". The deterministic JSON output, meaningful exit codes, cost-aware wake confirmation, and `--wake` opt-in flag make it safe for autonomous agent use without surprise billing.

## Features

- **Vehicle state queries** — battery, range, charge status, climate, location, doors, windows, trunks, tire pressure, dashcam, sentry mode, and more
- **Vehicle commands** — charge start/stop/limit/departure scheduling, climate on/off/set temp/seats/steering wheel, lock/unlock, sentry mode, trunk/frunk, windows, HomeLink, navigation waypoints, media playback, speed limits, PIN management
- **Vehicle Command Protocol** — ECDH session management with HMAC-SHA256 signed commands via the `signed_command` endpoint; automatically used when keys are enrolled
- **Key enrollment** — `tescmd key enroll <VIN>` sends your public key to the vehicle and guides you through Tesla app approval
- **Tier enforcement** — readonly tier blocks write commands with clear guidance to upgrade
- **Energy products** — Powerwall live status, site info, backup reserve, operation mode, storm mode, time-of-use settings, charging history, calendar history, grid import/export
- **User & sharing** — account info, region, orders, feature flags, driver management, vehicle sharing invites
- **Fleet Telemetry awareness** — setup wizard highlights Fleet Telemetry streaming for up to 97% API cost reduction
- **Response caching** — disk-based cache with configurable TTL reduces API costs; smart wake state tracking avoids redundant wake calls
- **Cost-aware wake** — prompts before sending billable wake API calls; `--wake` flag for scripts that accept the cost
- **Guided OAuth2 setup** — `tescmd auth login` walks you through browser-based authentication with PKCE
- **Key management** — generate EC keys, register via Tesla Developer Portal (remote) or BLE enrollment (proximity)
- **Rich terminal output** — tables, panels, spinners powered by Rich; auto-detects TTY vs pipe
- **Configurable display units** — switch between PSI/bar, °F/°C, and mi/km (defaults to US units)
- **JSON output** — structured output for scripting and agent integration
- **Multi-profile** — switch between vehicles, accounts, and regions with named profiles
- **Agent-friendly** — deterministic JSON, meaningful exit codes, `--wake` opt-in, headless auth support

## Quick Start

```bash
pip install tescmd

# First-time setup (interactive wizard)
tescmd setup

# Authenticate (opens browser)
tescmd auth login

# List your vehicles
tescmd vehicle list

# Get full vehicle data snapshot
tescmd vehicle info

# Check charge status (uses cache — second call is instant)
tescmd charge status

# Start charging (auto-invalidates cache)
tescmd charge start --wake

# Climate control
tescmd climate on --wake
tescmd climate set 72

# Lock the car
tescmd security lock --wake

# Enroll your key on a vehicle (required for signed commands)
tescmd key enroll 5YJ3E1EA1NF000000

# Cache management
tescmd cache status
tescmd cache clear
```

## Prerequisites

The following tools should be installed and authenticated before running `tescmd setup`:

| Tool | Required | Purpose | Auth |
|------|----------|---------|------|
| **Git** | Yes | Version control, repo management | N/A |
| **GitHub CLI** (`gh`) | Recommended | Auto-creates `*.github.io` domain for key hosting | `gh auth login` |
| **Tailscale** | Optional | Secure remote access to vehicles via Fleet Telemetry | `tailscale login` |

Without the GitHub CLI, you'll need to manually host your public key at the Tesla-required `.well-known` path on your own domain. Tailscale is only needed if you plan to use Fleet Telemetry streaming for reduced API costs.

## Installation

### From PyPI

```bash
pip install tescmd
```

### From Source

```bash
git clone https://github.com/oceanswave/tescmd.git
cd tescmd
pip install -e ".[dev]"
```

## Configuration

tescmd resolves settings in this order (highest priority first):

1. **CLI arguments** — `--vin`, `--region`, `--format`, etc.
2. **Environment variables** — `TESLA_VIN`, `TESLA_REGION`, etc. (`.env` files loaded automatically)
3. **Config profile** — `~/.config/tescmd/config.toml` (active profile)
4. **Defaults**

### Environment Variables

Create a `.env` file in your working directory or `~/.config/tescmd/.env`:

```dotenv
TESLA_CLIENT_ID=your-client-id
TESLA_CLIENT_SECRET=your-client-secret
TESLA_VIN=5YJ3E1EA1NF000000
TESLA_REGION=na

# Cache settings (optional)
TESLA_CACHE_ENABLED=true
TESLA_CACHE_TTL=60
TESLA_CACHE_DIR=~/.cache/tescmd

# Command protocol: auto | signed | unsigned (optional)
TESLA_COMMAND_PROTOCOL=auto
```

### Config File

```toml
# ~/.config/tescmd/config.toml

[default]
region = "na"
vin = "5YJ3E1EA1NF000000"
output_format = "rich"

[work-car]
region = "na"
vin = "7SA3E1EB2PF000000"
```

Switch profiles: `tescmd --profile work-car vehicle info`

## Commands

| Group | Commands | Description |
|---|---|---|
| `setup` | *(interactive wizard)* | First-run configuration: client ID, secret, region, domain, key enrollment |
| `auth` | `login`, `logout`, `status`, `refresh`, `register`, `export`, `import` | OAuth2 authentication lifecycle |
| `vehicle` | `list`, `info`, `data`, `location`, `wake`, `alerts`, `release-notes`, `service`, `drivers`, `low-power`, `accessory-power` | Vehicle discovery, state queries, wake, power management |
| `charge` | `status`, `start`, `stop`, `limit`, `limit-max`, `limit-std`, `amps`, `schedule`, `port-open`, `port-close`, `departure`, `add-schedule`, `remove-schedule`, `managed-amps` | Charge queries, control, scheduling, and fleet management |
| `climate` | `status`, `on`, `off`, `set`, `precondition`, `seat`, `seat-cool`, `wheel-heater`, `overheat`, `bioweapon`, `defrost`, `keeper`, `cop-temp`, `auto-seat`, `auto-wheel`, `wheel-level` | Climate, seat, and steering wheel control |
| `security` | `status`, `lock`, `unlock`, `sentry`, `valet`, `valet-reset`, `remote-start`, `flash`, `honk`, `boombox`, `speed-limit`, `pin-to-drive`, `pin-reset`, `pin-clear-admin`, `speed-clear`, `speed-clear-admin`, `guest-mode`, `erase-data` | Security, access, and PIN management |
| `trunk` | `open`, `close`, `frunk`, `window`, `sunroof`, `tonneau-open`, `tonneau-close`, `tonneau-stop` | Trunk, frunk, sunroof, tonneau, and window control |
| `media` | `play-pause`, `next-track`, `prev-track`, `next-fav`, `prev-fav`, `volume-up`, `volume-down`, `adjust-volume` | Media playback control |
| `nav` | `send`, `gps`, `supercharger`, `homelink`, `waypoints` | Navigation and HomeLink |
| `software` | `status`, `schedule`, `cancel` | Software update management |
| `energy` | `list`, `status`, `live`, `backup`, `mode`, `storm`, `tou`, `history`, `off-grid`, `grid-config`, `calendar` | Energy product (Powerwall) management |
| `user` | `me`, `region`, `orders`, `features` | User account information |
| `sharing` | `add-driver`, `remove-driver`, `create-invite`, `redeem-invite`, `revoke-invite`, `list-invites` | Vehicle sharing and driver management |
| `key` | `generate`, `deploy`, `validate`, `show`, `enroll` | Key management and enrollment |
| `cache` | `status`, `clear` | Response cache management |
| `raw` | `get`, `post` | Arbitrary Fleet API endpoint access |

Use `tescmd <group> --help` for detailed usage on any command group. For API endpoints not yet covered by a dedicated command, use `raw get` or `raw post` as an escape hatch.

### Global Flags

These flags can be placed at the root level or after any subcommand:

| Flag | Description |
|---|---|
| `--vin VIN` | Vehicle VIN (also accepted as a positional argument) |
| `--profile NAME` | Config profile name |
| `--format {rich,json,quiet}` | Force output format |
| `--quiet` | Suppress normal output |
| `--region {na,eu,cn}` | Tesla API region |
| `--verbose` | Enable verbose logging |
| `--no-cache` / `--fresh` | Bypass response cache for this invocation |
| `--wake` | Auto-wake vehicle without confirmation (billable) |

## Output Formats

tescmd auto-detects the best output format:

- **Rich** (default in TTY) — formatted tables, panels, colored status indicators
- **JSON** (`--format json` or piped) — structured, parseable output
- **Quiet** (`--quiet`) — minimal output on stderr, suitable for scripts that only check exit codes

```bash
# Human-friendly output
tescmd vehicle list

# JSON for scripting
tescmd vehicle list --format json

# Pipe-friendly (auto-switches to JSON)
tescmd vehicle list | jq '.[0].vin'

# Quiet mode (exit code only)
tescmd vehicle wake --quiet && echo "Vehicle is awake"
```

### Display Units

Rich output displays values in US units by default (°F, miles, PSI). The display unit system supports:

| Dimension | Default | Alternative |
|---|---|---|
| Temperature | °F | °C |
| Distance | mi | km |
| Pressure | psi | bar |

The Tesla API returns Celsius, miles, and bar — conversions happen in the display layer only.

## Tesla Fleet API Costs

Tesla's Fleet API is **pay-per-use** — every request returning a status code below 500 is billable, including 4xx errors like "vehicle asleep" (408) and rate limits (429). Wake requests are the most expensive category and are rate-limited to 3/min. There is no free tier (the $10/month credit is being discontinued).

> **Official pricing:** [Tesla Fleet API — Billing and Limits](https://developer.tesla.com/docs/fleet-api/billing-and-limits)

### Why This Matters

A naive script that polls `vehicle_data` every 5 minutes generates **4-5 billable requests per check** (asleep error + wake + poll + data fetch). That's **1,000+ billable requests per day** from a single cron job. At roughly $1 per 500 data requests, monitoring one vehicle costs around $60/month before you even count wake requests (the most expensive tier).

### Cost Example: Battery Check

| | Without tescmd | With tescmd |
|---|---|---|
| Vehicle asleep, check battery | 408 error (billable) + wake (billable) + poll (billable) + data (billable) = **4+ requests** | Cache miss → prompt user → user wakes via Tesla app (free) → retry → data (billable) = **1 request** |
| Check battery again 30s later | Another 4+ requests | **0 requests** (cache hit) |
| 10 checks in 1 minute | **40+ billable requests** | **1 billable request** + 9 cache hits |

### How tescmd Reduces Costs

tescmd implements three layers of cost protection:

1. **Response cache** — API responses are cached to disk (default 60s TTL). Repeated queries within the window return instantly with zero API calls.
2. **Wake state cache** — Tracks whether the vehicle was recently confirmed online (30s TTL). Skips redundant wake attempts.
3. **Wake confirmation prompt** — Prompts before sending billable wake calls in interactive mode. JSON/piped mode returns a structured error with `--wake` guidance.

```bash
# First call: hits API, caches response
tescmd charge status

# Second call within 60s: instant cache hit, no API call
tescmd charge status

# Bypass cache when you need fresh data
tescmd charge status --fresh

# Auto-wake without prompting (for scripts accepting the cost)
tescmd charge status --wake

# Manage cache
tescmd cache status              # entry counts, disk usage
tescmd cache clear               # clear all
tescmd cache clear --vin VIN     # clear for one vehicle
```

Write-commands (`charge start`, `climate on`, `security lock`, etc.) automatically invalidate the cache after success so that subsequent reads reflect the new state.

For the full cost breakdown with more examples, savings calculations, and Fleet Telemetry streaming comparison, see [docs/api-costs.md](docs/api-costs.md).

Configure via environment variables:

| Variable | Default | Description |
|---|---|---|
| `TESLA_CACHE_ENABLED` | `true` | Enable/disable the cache |
| `TESLA_CACHE_TTL` | `60` | Time-to-live in seconds |
| `TESLA_CACHE_DIR` | `~/.cache/tescmd` | Cache directory path |

## Key Enrollment & Vehicle Command Protocol

Newer Tesla vehicles require commands to be signed using the [Vehicle Command Protocol](https://github.com/teslamotors/vehicle-command). tescmd handles this transparently:

1. **Generate a key pair** — `tescmd key generate` creates an EC P-256 key pair
2. **Enroll on vehicle** — `tescmd key enroll <VIN>` sends the public key to the vehicle; approve in the Tesla app
3. **Commands are signed automatically** — once enrolled, tescmd uses ECDH sessions + HMAC-SHA256 to sign commands via the `signed_command` endpoint

```bash
# Generate EC key pair
tescmd key generate

# Enroll on a vehicle (interactive approval via Tesla app)
tescmd key enroll 5YJ3E1EA1NF000000

# Commands are now signed automatically
tescmd security lock --wake
```

The `command_protocol` setting controls routing:

| Value | Behavior |
|---|---|
| `auto` (default) | Use signed path when keys are enrolled; fall back to unsigned |
| `signed` | Require signed commands (error if no keys) |
| `unsigned` | Force legacy REST path (skip signing) |

Set via `TESLA_COMMAND_PROTOCOL` environment variable or in your config.

See [docs/vehicle-command-protocol.md](docs/vehicle-command-protocol.md) for the full protocol architecture.

## Agent Integration

tescmd is designed for use by AI agents and automation platforms. Agents like [Claude Code](https://github.com/anthropics/claude-code), Claude Desktop, and other LLM-powered tools can invoke tescmd commands, parse the structured JSON output, and act on your behalf.

**Why tescmd works well as an agent tool:**

- **Structured JSON output** — piped/non-TTY mode automatically emits parseable JSON with consistent schema
- **Cost protection** — agents won't accidentally trigger billable wake calls without `--wake`; the default behavior is safe
- **Cache-aware** — repeated queries from an agent within the TTL window cost nothing
- **Meaningful exit codes** — agents can branch on success/failure without parsing output
- **Stateless invocations** — each command is self-contained; no session state to manage
- **Signed commands** — when keys are enrolled, commands are signed transparently; no agent-side crypto needed

**Example agent workflow:**

```bash
# Agent checks battery (cache hit if recent)
tescmd charge status --format json

# Agent decides to start charging
tescmd charge start --wake --format json

# Agent verifies the command took effect (cache was invalidated)
tescmd charge status --format json --fresh
```

See [docs/bot-integration.md](docs/bot-integration.md) for the full JSON schema, exit code reference, and headless authentication setup.

## Development

```bash
# Clone and install in dev mode
git clone https://github.com/oceanswave/tescmd.git
cd tescmd
pip install -e ".[dev]"

# Run checks
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
pytest

# Run a specific test
pytest tests/cli/test_auth.py -v
```

See [docs/development.md](docs/development.md) for detailed contribution guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT
