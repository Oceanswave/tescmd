# Development Guide

## Prerequisites

- Python 3.11+
- Git
- A Tesla Developer account (for integration testing)

## Setup

```bash
# Clone the repo
git clone https://github.com/oceanswave/tescmd.git
cd tescmd

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in dev mode with all extras
pip install -e ".[dev]"
```

The `[dev]` extra installs:
- `pytest`, `pytest-asyncio`, `pytest-httpx` — testing
- `ruff` — linting and formatting
- `mypy` — static type checking
- `build` — package building

## Project Layout

```
tescmd/
├── src/tescmd/          # Source code (src layout)
│   ├── cli/             # CLI layer (Click command groups)
│   ├── api/             # API client layer (HTTP, domain methods)
│   ├── models/          # Pydantic v2 models
│   ├── auth/            # OAuth2, token storage
│   ├── crypto/          # EC keys, ECDH key exchange
│   ├── protocol/        # Vehicle Command Protocol (ECDH, signing, protobuf)
│   ├── output/          # Rich + JSON formatters, display units
│   ├── cache/           # Response caching (file-based JSON with TTL)
│   ├── deploy/          # Key deployment (GitHub Pages)
│   ├── config/          # Configuration (stub)
│   ├── ble/             # BLE key enrollment (stub)
│   └── _internal/       # Shared utilities
├── tests/               # Test files (mirrors src/ structure)
│   ├── cli/
│   ├── api/
│   ├── models/
│   ├── auth/
│   ├── crypto/
│   ├── output/
│   ├── cache/
│   ├── deploy/
│   ├── protocol/        # Vehicle Command Protocol tests
│   └── conftest.py      # Shared fixtures
├── scripts/             # Developer scripts
├── docs/                # Documentation
├── pyproject.toml       # Build config, deps, tool config
├── CLAUDE.md            # Claude Code context
└── README.md            # User-facing docs
```

## Running Checks

```bash
# All checks (run before committing)
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
pytest

# Quick check during development
ruff check src/ tests/ && mypy src/ && pytest
```

### Linting with ruff

ruff handles both linting and formatting:

```bash
# Lint
ruff check src/ tests/

# Auto-fix safe issues
ruff check --fix src/ tests/

# Format
ruff format src/ tests/

# Check formatting without changes
ruff format --check src/ tests/
```

Configuration is in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py311"
line-length = 99

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # ruff-specific rules
]
```

### Type Checking with mypy

```bash
mypy src/
```

mypy runs in strict mode. All code must be fully typed:

```toml
[tool.mypy]
strict = true
python_version = "3.11"
```

### Testing with pytest

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/cli/test_auth.py

# Run tests matching a pattern
pytest -k "test_charge"

# Run with coverage
pytest --cov=tescmd --cov-report=term-missing
```

Configuration:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

## Writing Tests

### Test File Structure

Tests mirror the source structure:

```
src/tescmd/cli/vehicle.py   →  tests/cli/test_cli_integration.py
src/tescmd/api/client.py    →  tests/api/test_client.py
src/tescmd/auth/oauth.py    →  tests/auth/test_oauth.py
src/tescmd/output/rich_output.py → tests/output/test_rich_output.py
```

### Mocking HTTP Calls

Use `pytest-httpx` to mock Fleet API responses. Never make real API calls in tests:

```python
import pytest
from tescmd.api.client import TeslaFleetClient

@pytest.mark.asyncio
async def test_list_vehicles(httpx_mock):
    httpx_mock.add_response(
        url="https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles",
        json={
            "response": [
                {"vin": "5YJ3E1EA1NF000000", "display_name": "My Model 3", "state": "online"}
            ],
            "count": 1,
        },
    )

    client = TeslaFleetClient(access_token="test-token", region="na")
    vehicles = await client.get("/api/1/vehicles")
    assert len(vehicles["response"]) == 1
    assert vehicles["response"][0]["vin"] == "5YJ3E1EA1NF000000"
```

### Testing Async Code

All API tests are async. Use `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_get_vehicle_data(httpx_mock):
    httpx_mock.add_response(
        url="https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/VIN123/vehicle_data",
        json={"response": {"vin": "VIN123", "charge_state": {"battery_level": 80}}},
    )

    client = TeslaFleetClient(access_token="test-token", region="na")
    vehicle_api = VehicleAPI(client)
    data = await vehicle_api.get_vehicle_data("VIN123")
    assert data.charge_state.battery_level == 80
```

### Testing Rich Output

Test Rich output by capturing to a `StringIO` buffer:

```python
from io import StringIO
from rich.console import Console
from tescmd.output.rich_output import RichOutput, DisplayUnits, TempUnit

def test_climate_status_fahrenheit():
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    ro = RichOutput(console)  # defaults to US units

    cs = ClimateState(inside_temp=22.0, is_climate_on=True)
    ro.climate_status(cs)
    output = buf.getvalue()

    assert "71.6" in output  # 22°C → 71.6°F

def test_climate_status_celsius():
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    ro = RichOutput(console, units=DisplayUnits(temp=TempUnit.C))

    cs = ClimateState(inside_temp=22.0, is_climate_on=True)
    ro.climate_status(cs)
    output = buf.getvalue()

    assert "22.0°C" in output
```

### Shared Fixtures

Define common fixtures in `tests/conftest.py`:

```python
import pytest
from tescmd.api.client import TeslaFleetClient

@pytest.fixture
def mock_client(httpx_mock):
    """Pre-configured client for testing."""
    return TeslaFleetClient(access_token="test-token", region="na")

@pytest.fixture
def sample_vehicle_data():
    """Sample vehicle data response."""
    return {
        "response": {
            "vin": "5YJ3E1EA1NF000000",
            "charge_state": {"battery_level": 72, "charging_state": "Disconnected"},
            "climate_state": {"inside_temp": 21.5, "outside_temp": 15.0},
            "drive_state": {"latitude": 37.3861, "longitude": -122.0839},
            "vehicle_state": {"locked": True, "odometer": 15234.5},
        }
    }
```

## Adding a New Command

This walks through adding a new command group or subcommand using Click.

### Step 1: Add the CLI Module

Create `src/tescmd/cli/charge.py` (example: charge commands):

```python
"""CLI commands for charge control."""

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._options import vin_argument

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext


@click.group("charge")
def charge_group() -> None:
    """Charge queries and control."""


@charge_group.command("status")
@vin_argument
@click.pass_obj
def charge_status(ctx: AppContext, vin: str | None) -> None:
    """Display current charging state."""
    resolved_vin = vin or ctx.vin
    if not resolved_vin:
        raise click.UsageError("No VIN specified. Use --vin or set TESLA_VIN.")
    data = run_async(_fetch_charge_status(resolved_vin, ctx))
    ctx.formatter.charge_status(data)


@charge_group.command("start")
@vin_argument
@click.pass_obj
def charge_start(ctx: AppContext, vin: str | None) -> None:
    """Start charging."""
    resolved_vin = vin or ctx.vin
    if not resolved_vin:
        raise click.UsageError("No VIN specified.")
    result = run_async(_start_charge(resolved_vin, ctx))
    ctx.formatter.command_result(result)


async def _fetch_charge_status(vin: str, ctx: AppContext):
    # Build API client, call VehicleAPI.get_vehicle_data with charge_state endpoint
    ...


async def _start_charge(vin: str, ctx: AppContext):
    # Build API client, call CommandAPI.start_charge
    ...
```

### Step 2: Register in Main

Add to `src/tescmd/cli/main.py` in `_register_commands()`:

```python
def _register_commands() -> None:
    from tescmd.cli.auth import auth_group
    from tescmd.cli.charge import charge_group  # new
    from tescmd.cli.key import key_group
    from tescmd.cli.setup import setup_cmd
    from tescmd.cli.vehicle import vehicle_group

    cli.add_command(auth_group)
    cli.add_command(charge_group)  # new
    cli.add_command(key_group)
    cli.add_command(setup_cmd)
    cli.add_command(vehicle_group)
```

### Step 3: Add Rich Output Method

Add a method to `src/tescmd/output/rich_output.py`:

```python
def charge_status(self, cs: ChargeState) -> None:
    table = Table(title="Charge Status")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    if cs.battery_level is not None:
        table.add_row("Battery %", f"{cs.battery_level}%")
    if cs.battery_range is not None:
        table.add_row("Range", self._fmt_dist(cs.battery_range))
    # ... more fields
    self._con.print(table)
```

### Step 4: Add Tests

Create `tests/cli/test_charge.py`:

```python
import pytest
from click.testing import CliRunner
from tescmd.cli.main import cli

def test_charge_status(httpx_mock):
    httpx_mock.add_response(
        url="...",
        json={"response": {"charge_state": {"battery_level": 80}}},
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["charge", "status", "--vin", "VIN123"])
    assert result.exit_code == 0
    assert "80%" in result.output
```

### Step 5: Update Documentation

- Add command group to `docs/commands.md`
- Add to the command table in `README.md`

### Checklist for New Commands

- [ ] CLI module in `src/tescmd/cli/` with Click group and commands
- [ ] API methods in appropriate `src/tescmd/api/` module
- [ ] Pydantic models for any new response shapes in `src/tescmd/models/`
- [ ] Rich output formatting for new data types in `src/tescmd/output/rich_output.py`
- [ ] Tests in `tests/` mirroring source structure
- [ ] Docs updated: `docs/commands.md` and `README.md` command table
- [ ] `ruff check`, `mypy`, `pytest` all pass

## E2E Testing Against a Live Vehicle

The `tests/cli/test_e2e_smoke.py` suite runs every tescmd command against the live Tesla Fleet API. It is excluded from normal `pytest` runs and requires explicit invocation.

**Prerequisites:** Set `TESLA_ACCESS_TOKEN` (and optionally other credentials) in your environment. Set `E2E_VIN` and `E2E_SITE_ID` for your vehicle and energy site.

```bash
# Run all e2e tests (sequential, verbose)
pytest -m e2e -v -n 0

# Stop on first failure
pytest -m e2e -x -v -n 0

# Run a specific category
pytest -m e2e -v -n 0 -k "TestReadVehicleCommands"
pytest -m e2e -v -n 0 -k "TestBenignWriteCommands"
pytest -m e2e -v -n 0 -k "TestHelpOnlyCommands"
```

**Test categories:**

| Category | Tests | What it does |
|----------|-------|-------------|
| `TestReadVehicleCommands` | 19 | Vehicle data reads with `--wake` |
| `TestReadStatusCommands` | 4 | Charge/climate/security/software status |
| `TestReadEnergyCommands` | 5 | Energy product reads |
| `TestReadOtherCommands` | 14 | Billing, user, sharing, auth, key, cache, partner, raw |
| `TestBenignWriteCommands` | 9 | Safe writes with save/restore (flash, honk, climate, etc.) |
| `TestHelpOnlyCommands` | 128 | `--help` on every command — validates Click wiring |

## Building

```bash
# Build wheel and sdist
python -m build

# The output goes to dist/
ls dist/
# tescmd-0.1.0-py3-none-any.whl
# tescmd-0.1.0.tar.gz
```

## Code Style Quick Reference

- **Type hints** on all function signatures and non-obvious variables
- **async/await** for all I/O operations
- **Pydantic models** for all structured data (no raw dicts crossing module boundaries)
- **Composition** — inject dependencies via constructor, don't inherit
- **No star imports** — `from module import *` is never used
- **Line length** — 99 characters
- **Docstrings** — required on public functions and classes, Google style
- **Naming** — `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants
