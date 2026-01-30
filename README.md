# tescmd

<!-- [![PyPI](https://img.shields.io/pypi/v/tescmd)](https://pypi.org/project/tescmd/) -->
<!-- [![Python](https://img.shields.io/pypi/pyversions/tescmd)](https://pypi.org/project/tescmd/) -->
[![License](https://img.shields.io/github/license/oceanswave/tescmd)](LICENSE)

A Python CLI for querying and controlling Tesla vehicles via the Fleet API — built for both human operators and AI agents.

## Why tescmd?

Tesla's Fleet API gives developers full access to vehicle data and commands, but working with it directly means juggling OAuth2 PKCE flows, token refresh, regional endpoints, key enrollment, and raw JSON responses. tescmd wraps all of that into a single command-line tool that handles authentication, token management, and output formatting so you can focus on what you actually want to do — check your battery, find your car, or control your vehicle.

tescmd is designed to work as a tool that AI agents can invoke directly. Platforms like [OpenClaude](https://github.com/anthropics/claude-code), [Claude Desktop](https://claude.ai), and other agent frameworks can call tescmd commands, parse the structured JSON output, and take actions on your behalf — "lock my car", "what's my battery at?", "start climate control". The deterministic JSON output, meaningful exit codes, cost-aware wake confirmation, and `--wake` opt-in flag make it safe for autonomous agent use without surprise billing.

## Features

- **Vehicle state queries** — battery, range, charge status, climate, location, doors, windows, trunks, tire pressure, dashcam, sentry mode, and more
- **Vehicle commands** — charge start/stop/limit/departure scheduling, climate on/off/set temp/seats/steering wheel, lock/unlock, sentry mode, trunk/frunk, windows, HomeLink, navigation waypoints, media playback, speed limits, PIN management
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

# Cache management
tescmd cache status
tescmd cache clear
```

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
| `setup` | *(interactive wizard)* | First-run configuration: client ID, secret, region, domain |
| `auth` | `login`, `logout`, `status`, `refresh`, `register`, `export`, `import` | OAuth2 authentication lifecycle |
| `vehicle` | `list`, `info`, `data`, `location`, `wake`, `alerts`, `release-notes`, `service`, `drivers` | Vehicle discovery, state queries, wake, service data |
| `charge` | `status`, `start`, `stop`, `limit`, `limit-max`, `limit-std`, `amps`, `schedule`, `port-open`, `port-close`, `departure`, `precondition-add`, `precondition-remove` | Charge queries, control, and scheduling |
| `climate` | `status`, `on`, `off`, `set`, `precondition`, `seat`, `seat-cool`, `wheel-heater`, `overheat`, `keeper`, `cop-temp`, `auto-seat`, `auto-wheel`, `wheel-level` | Climate, seat, and steering wheel control |
| `security` | `status`, `lock`, `unlock`, `sentry`, `valet`, `valet-reset`, `remote-start`, `flash`, `honk`, `speed-limit`, `pin-reset`, `pin-clear-admin`, `speed-clear`, `speed-clear-admin` | Security, access, and PIN management |
| `trunk` | `open`, `close`, `frunk`, `window` | Trunk, frunk, and window control |
| `media` | `play-pause`, `next-track`, `prev-track`, `next-fav`, `prev-fav`, `volume-up`, `volume-down`, `adjust-volume` | Media playback control |
| `nav` | `send`, `gps`, `supercharger`, `homelink`, `waypoints` | Navigation and HomeLink |
| `software` | `status`, `schedule`, `cancel` | Software update management |
| `energy` | `list`, `status`, `live`, `backup`, `mode`, `storm`, `tou`, `history`, `off-grid`, `grid-config`, `calendar` | Energy product (Powerwall) management |
| `user` | `me`, `region`, `orders`, `features` | User account information |
| `sharing` | `add-driver`, `remove-driver`, `create-invite`, `redeem-invite`, `revoke-invite`, `list-invites` | Vehicle sharing and driver management |
| `key` | `generate`, `register`, `list` | Key management and enrollment |
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

## Response Cache

Tesla's Fleet API is pay-per-use — every call with status < 500 is billable. Wake requests are the most expensive category (3/min rate limit). tescmd reduces costs with a three-layer optimization:

1. **Disk cache** — API responses are cached as JSON files under `~/.cache/tescmd/` with a configurable TTL (default 60s). Repeated queries within the TTL window return instantly from disk.
2. **Wake state cache** — Tracks whether the vehicle was recently confirmed online (30s TTL). If the vehicle is known to be awake, the cache skips the wake attempt entirely.
3. **Wake confirmation** — Before sending a billable wake API call, tescmd prompts for confirmation in interactive mode, or returns a structured error in JSON/piped mode.

```bash
# First call: hits API, caches response
tescmd charge status

# Second call within 60s: instant cache hit
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

Configure via environment variables:

| Variable | Default | Description |
|---|---|---|
| `TESLA_CACHE_ENABLED` | `true` | Enable/disable the cache |
| `TESLA_CACHE_TTL` | `60` | Time-to-live in seconds |
| `TESLA_CACHE_DIR` | `~/.cache/tescmd` | Cache directory path |

## Agent Integration

tescmd is designed for use by AI agents and automation platforms. Agents like [Claude Code](https://github.com/anthropics/claude-code), Claude Desktop, and other LLM-powered tools can invoke tescmd commands, parse the structured JSON output, and act on your behalf.

**Why tescmd works well as an agent tool:**

- **Structured JSON output** — piped/non-TTY mode automatically emits parseable JSON with consistent schema
- **Cost protection** — agents won't accidentally trigger billable wake calls without `--wake`; the default behavior is safe
- **Cache-aware** — repeated queries from an agent within the TTL window cost nothing
- **Meaningful exit codes** — agents can branch on success/failure without parsing output
- **Stateless invocations** — each command is self-contained; no session state to manage

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
