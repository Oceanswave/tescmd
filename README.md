# tescmd

<!-- Badges -->
<!-- [![PyPI](https://img.shields.io/pypi/v/tescmd)](https://pypi.org/project/tescmd/) -->
<!-- [![Python](https://img.shields.io/pypi/pyversions/tescmd)](https://pypi.org/project/tescmd/) -->
<!-- [![License](https://img.shields.io/github/license/oceanswave/tescmd)](LICENSE) -->

A Python CLI for querying and controlling Tesla vehicles via the Fleet API.

## Features

- **Full Fleet API coverage** — vehicle state queries (battery, location, climate, drive state) and 80+ vehicle commands (charge, climate, security, media, navigation, trunk, software, and more)
- **Guided OAuth2 setup** — `tescmd auth login` walks you through browser-based authentication with PKCE
- **Key management** — generate EC keys, register via Tesla Developer Portal (remote) or BLE enrollment (proximity)
- **Rich terminal output** — tables, panels, spinners powered by Rich; auto-detects TTY vs pipe
- **JSON output** — structured output for scripting and bot integration
- **Multi-profile** — switch between vehicles, accounts, and regions with named profiles
- **Bot-friendly** — deterministic JSON, meaningful exit codes, headless auth support

## Quick Start

```bash
pip install tescmd

# Authenticate (opens browser)
tescmd auth login

# List your vehicles
tescmd vehicle list

# Check battery level and charge status
tescmd charge status

# Get current location
tescmd vehicle location

# Check interior/exterior temperature
tescmd climate status

# Start charging
tescmd charge start

# Set climate to 72°F
tescmd climate set --temp 72
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
| `auth` | `login`, `logout`, `status`, `refresh` | OAuth2 authentication lifecycle |
| `vehicle` | `list`, `info`, `data`, `location`, `wake` | Vehicle discovery, state queries, wake |
| `charge` | `status`, `start`, `stop`, `limit`, `port-open`, `port-close`, `schedule` | Charge queries and control |
| `climate` | `status`, `on`, `off`, `set`, `precondition`, `defrost`, `seat-heater`, `bioweapon` | Climate queries and control |
| `security` | `status`, `lock`, `unlock`, `remote-start`, `speed-limit`, `valet`, `sentry` | Security queries and control |
| `media` | `status`, `play`, `pause`, `next`, `prev`, `volume-up`, `volume-down`, `toggle-playback` | Media queries and control |
| `nav` | `set`, `waypoint`, `sc`, `home`, `work` | Navigation destinations |
| `trunk` | `open`, `close`, `frunk` | Trunk and frunk control |
| `software` | `status`, `update`, `cancel` | Software update queries and management |
| `key` | `generate`, `register`, `list`, `delete` | Key management and BLE enrollment |
| `fleet` | `status`, `telemetry` | Fleet-wide operations |
| `raw` | `get`, `post` | Arbitrary Fleet API endpoint access |

Use `tescmd <group> --help` for detailed usage on any command group.

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
tescmd charge start --quiet && echo "Charging started"
```

## Bot Integration

tescmd is designed for automation. See [docs/bot-integration.md](docs/bot-integration.md) for:

- JSON output format specification
- Exit code reference
- Headless authentication setup
- Environment variable configuration
- Piping and scripting patterns

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

## License

MIT
