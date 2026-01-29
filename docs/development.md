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
│   ├── cli/             # CLI layer (argparse, dispatch, output)
│   ├── api/             # API client layer (HTTP, domain methods)
│   ├── models/          # Pydantic v2 models
│   ├── auth/            # OAuth2, token storage
│   ├── crypto/          # EC keys, command signing
│   ├── output/          # Rich + JSON formatters
│   ├── config/          # Settings, profiles
│   ├── ble/             # BLE key enrollment
│   └── _internal/       # Shared utilities
├── tests/               # Test files (mirrors src/ structure)
│   ├── cli/
│   ├── api/
│   ├── models/
│   ├── auth/
│   ├── crypto/
│   ├── output/
│   └── conftest.py      # Shared fixtures
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
src/tescmd/cli/charge.py    →  tests/cli/test_charge.py
src/tescmd/api/client.py    →  tests/api/test_client.py
src/tescmd/auth/oauth.py    →  tests/auth/test_oauth.py
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
async def test_start_charge(httpx_mock):
    httpx_mock.add_response(
        url="https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/VIN123/command/charge_start",
        json={"response": {"result": True, "reason": ""}},
    )

    client = TeslaFleetClient(access_token="test-token", region="na")
    command_api = CommandAPI(client)
    result = await command_api.start_charge("VIN123")
    assert result.result is True
```

### Testing CLI Output

Test CLI commands by capturing output:

```python
from io import StringIO
from unittest.mock import patch

def test_vehicle_list_json(httpx_mock):
    httpx_mock.add_response(...)

    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        # Run CLI command with --format json
        main(["vehicle", "list", "--format", "json"])

    output = json.loads(mock_stdout.getvalue())
    assert output["ok"] is True
    assert len(output["data"]) == 1
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

This walks through adding a new command group or subcommand.

### Step 1: Add the CLI Module

Create `src/tescmd/cli/windows.py` (example: window control commands):

```python
"""CLI commands for window control."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tescmd.api.command import CommandAPI
    from tescmd.output.formatter import OutputFormatter

def register(subparsers: argparse._SubParsersAction) -> None:
    """Register window commands with the argument parser."""
    parser = subparsers.add_parser("windows", help="Window control")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # windows status
    status_parser = sub.add_parser("status", help="Get window state")
    status_parser.set_defaults(func=cmd_status)

    # windows vent
    vent_parser = sub.add_parser("vent", help="Vent all windows")
    vent_parser.set_defaults(func=cmd_vent)

    # windows close
    close_parser = sub.add_parser("close", help="Close all windows")
    close_parser.set_defaults(func=cmd_close)


async def cmd_status(
    args: argparse.Namespace,
    command_api: CommandAPI,
    formatter: OutputFormatter,
) -> int:
    """Query window state."""
    data = await command_api.get_vehicle_data(args.vin, endpoints=["vehicle_state"])
    formatter.output(data, command="windows.status")
    return 0


async def cmd_vent(
    args: argparse.Namespace,
    command_api: CommandAPI,
    formatter: OutputFormatter,
) -> int:
    """Vent all windows."""
    result = await command_api.vent_windows(args.vin)
    formatter.output(result, command="windows.vent")
    return 0


async def cmd_close(
    args: argparse.Namespace,
    command_api: CommandAPI,
    formatter: OutputFormatter,
) -> int:
    """Close all windows."""
    result = await command_api.close_windows(args.vin)
    formatter.output(result, command="windows.close")
    return 0
```

### Step 2: Add API Methods

Add methods to `src/tescmd/api/command.py`:

```python
async def vent_windows(self, vin: str) -> CommandResponse:
    return await self._client.post(
        f"/api/1/vehicles/{vin}/command/window_control",
        json={"command": "vent"},
    )

async def close_windows(self, vin: str) -> CommandResponse:
    return await self._client.post(
        f"/api/1/vehicles/{vin}/command/window_control",
        json={"command": "close"},
    )
```

### Step 3: Register in Main

Add to `src/tescmd/cli/main.py`:

```python
from tescmd.cli import windows

# In the parser setup:
windows.register(subparsers)
```

### Step 4: Add Tests

Create `tests/cli/test_windows.py`:

```python
import pytest

@pytest.mark.asyncio
async def test_vent_windows(httpx_mock):
    httpx_mock.add_response(
        url="https://fleet-api.prd.na.vn.cloud.tesla.com/api/1/vehicles/VIN123/command/window_control",
        json={"response": {"result": True, "reason": ""}},
    )
    # ... test implementation
```

### Step 5: Update Documentation

- Add command group to `docs/commands.md`
- Add to the command table in `README.md`

### Checklist for New Commands

- [ ] CLI module in `src/tescmd/cli/` with `register()` function
- [ ] API methods in appropriate `src/tescmd/api/` module
- [ ] Pydantic models for any new response shapes in `src/tescmd/models/`
- [ ] Rich output formatting for new data types in `src/tescmd/output/rich_output.py`
- [ ] Tests in `tests/` mirroring source structure
- [ ] Docs updated: `docs/commands.md` and `README.md` command table
- [ ] `ruff check`, `mypy`, `pytest` all pass

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
