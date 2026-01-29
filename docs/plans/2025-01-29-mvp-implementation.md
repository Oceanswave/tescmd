# MVP Implementation Plan: Auth + Vehicle Data

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Working CLI that authenticates via OAuth2 PKCE and queries vehicle data (list, info, location) from the Tesla Fleet API.

**Architecture:** Bottom-up build through 3 phases — foundation (models, config, output), HTTP client + auth, then vehicle API + CLI. Each phase produces testable code. Composition pattern: CLI → API → Client layers, pydantic models as contracts between them.

**Tech Stack:** Python 3.11+, pydantic v2, httpx, rich, keyring, python-dotenv, argparse, cryptography (for future key mgmt), hatchling build system. Testing: pytest + pytest-asyncio + pytest-httpx. Linting: ruff + mypy strict.

---

## Phase A: Foundation

### Task 1: Project Skeleton — pyproject.toml + Package Init

**Files:**
- Create: `pyproject.toml`
- Create: `src/tescmd/__init__.py`
- Create: `src/tescmd/__main__.py`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "tescmd"
version = "0.1.0"
description = "A Python CLI for querying and controlling Tesla vehicles via the Fleet API"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [{ name = "oceanswave" }]
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "rich>=13.0",
    "keyring>=25.0",
    "python-dotenv>=1.0",
    "cryptography>=42.0",
]

[project.optional-dependencies]
ble = ["bleak>=0.22"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.34",
    "pytest-cov>=5.0",
    "ruff>=0.8",
    "mypy>=1.13",
    "build>=1.0",
]

[project.scripts]
tescmd = "tescmd.cli.main:main"

[tool.hatch.build.targets.wheel]
packages = ["src/tescmd"]

[tool.ruff]
target-version = "py311"
line-length = 99
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E", "W", "F", "I", "N", "UP", "B", "SIM", "TCH", "RUF",
]

[tool.mypy]
strict = true
python_version = "3.11"
plugins = ["pydantic.mypy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

**Step 2: Create package init**

```python
# src/tescmd/__init__.py
"""tescmd — A Python CLI for querying and controlling Tesla vehicles via the Fleet API."""

__version__ = "0.1.0"
```

**Step 3: Create __main__.py**

```python
# src/tescmd/__main__.py
"""Allow running as: python -m tescmd"""

from tescmd.cli.main import main

main()
```

**Step 4: Create directory structure**

```bash
mkdir -p src/tescmd/{cli,api,models,auth,output,config,crypto,ble,_internal}
mkdir -p tests/{cli,api,auth,models,output}
touch src/tescmd/cli/__init__.py
touch src/tescmd/api/__init__.py
touch src/tescmd/models/__init__.py
touch src/tescmd/auth/__init__.py
touch src/tescmd/output/__init__.py
touch src/tescmd/config/__init__.py
touch src/tescmd/crypto/__init__.py
touch src/tescmd/ble/__init__.py
touch src/tescmd/_internal/__init__.py
touch tests/__init__.py tests/cli/__init__.py tests/api/__init__.py
touch tests/auth/__init__.py tests/models/__init__.py tests/output/__init__.py
```

**Step 5: Create .gitignore**

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.venv/
.env
*.pem
.mypy_cache/
.pytest_cache/
.ruff_cache/
.coverage
```

**Step 6: Install in dev mode and verify**

```bash
pip install -e ".[dev]"
```

Expected: installs successfully with all dependencies.

**Step 7: Commit**

```bash
git init
git add pyproject.toml src/ tests/ .gitignore CLAUDE.md README.md docs/
git commit -m "feat: project skeleton with pyproject.toml and package structure"
```

---

### Task 2: Pydantic Models — Config

**Files:**
- Create: `src/tescmd/models/config.py`
- Create: `tests/models/test_config.py`

**Step 1: Write the failing test**

```python
# tests/models/test_config.py
"""Tests for config models."""

from tescmd.models.config import AppSettings, Profile


def test_profile_defaults():
    profile = Profile()
    assert profile.region == "na"
    assert profile.vin is None
    assert profile.output_format is None


def test_profile_with_values():
    profile = Profile(region="eu", vin="5YJ3E1EA1NF000000", output_format="json")
    assert profile.region == "eu"
    assert profile.vin == "5YJ3E1EA1NF000000"
    assert profile.output_format == "json"


def test_app_settings_defaults(monkeypatch: object):
    """AppSettings loads defaults when no env vars are set."""
    import os

    # Clear any Tesla env vars that might be set
    for key in list(os.environ):
        if key.startswith("TESLA_"):
            monkeypatch.delenv(key, raising=False)  # type: ignore[union-attr]

    settings = AppSettings()
    assert settings.tesla_region == "na"
    assert settings.tesla_vin is None
    assert settings.tesla_client_id is None


def test_app_settings_from_env(monkeypatch: object):
    """AppSettings reads from environment variables."""
    monkeypatch.setenv("TESLA_CLIENT_ID", "test-id")  # type: ignore[union-attr]
    monkeypatch.setenv("TESLA_REGION", "eu")  # type: ignore[union-attr]
    monkeypatch.setenv("TESLA_VIN", "VIN123")  # type: ignore[union-attr]

    settings = AppSettings()
    assert settings.tesla_client_id == "test-id"
    assert settings.tesla_region == "eu"
    assert settings.tesla_vin == "VIN123"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_config.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/models/config.py
"""Configuration models."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Profile(BaseModel):
    """A named configuration profile."""

    region: str = "na"
    vin: str | None = None
    output_format: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class AppSettings(BaseSettings):
    """Application settings loaded from environment variables and .env files.

    Resolution order: env vars > .env file > defaults.
    CLI args override these at runtime (handled in cli/main.py).
    """

    tesla_client_id: str | None = None
    tesla_client_secret: str | None = None
    tesla_vin: str | None = None
    tesla_region: str = "na"
    tesla_token_file: str | None = None
    tesla_config_dir: str = "~/.config/tescmd"
    tesla_output_format: str | None = None
    tesla_profile: str = "default"
    tesla_access_token: str | None = None
    tesla_refresh_token: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/models/test_config.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tescmd/models/config.py tests/models/test_config.py
git commit -m "feat: add config models (AppSettings, Profile)"
```

---

### Task 3: Pydantic Models — Auth

**Files:**
- Create: `src/tescmd/models/auth.py`
- Create: `tests/models/test_auth.py`

**Step 1: Write the failing test**

```python
# tests/models/test_auth.py
"""Tests for auth models."""

from tescmd.models.auth import AuthConfig, TokenData


def test_token_data_from_response():
    data = TokenData(
        access_token="eyJ_access",
        refresh_token="eyJ_refresh",
        expires_in=28800,
        token_type="Bearer",
    )
    assert data.access_token == "eyJ_access"
    assert data.refresh_token == "eyJ_refresh"
    assert data.expires_in == 28800
    assert data.token_type == "Bearer"


def test_token_data_optional_fields():
    data = TokenData(
        access_token="eyJ_access",
        token_type="Bearer",
        expires_in=28800,
    )
    assert data.refresh_token is None


def test_auth_config():
    config = AuthConfig(
        client_id="test-client",
        client_secret="test-secret",
        redirect_uri="http://localhost:8085/callback",
        scopes=["openid", "vehicle_device_data"],
    )
    assert config.client_id == "test-client"
    assert config.redirect_uri == "http://localhost:8085/callback"
    assert len(config.scopes) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_auth.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/models/auth.py
"""Authentication models."""

from __future__ import annotations

from pydantic import BaseModel


DEFAULT_SCOPES = [
    "openid",
    "vehicle_device_data",
    "vehicle_cmds",
    "vehicle_charging_cmds",
    "offline_access",
]

DEFAULT_REDIRECT_URI = "http://localhost:8085/callback"
AUTH_BASE_URL = "https://auth.tesla.com"
AUTHORIZE_URL = f"{AUTH_BASE_URL}/oauth2/v3/authorize"
TOKEN_URL = f"{AUTH_BASE_URL}/oauth2/v3/token"


class TokenData(BaseModel):
    """Token response from Tesla OAuth2 endpoint."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None


class TokenMeta(BaseModel):
    """Metadata stored alongside tokens in keyring."""

    expires_at: float
    scopes: list[str]
    region: str


class AuthConfig(BaseModel):
    """OAuth2 configuration for authentication."""

    client_id: str
    client_secret: str | None = None
    redirect_uri: str = DEFAULT_REDIRECT_URI
    scopes: list[str] = DEFAULT_SCOPES
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/models/test_auth.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tescmd/models/auth.py tests/models/test_auth.py
git commit -m "feat: add auth models (TokenData, TokenMeta, AuthConfig)"
```

---

### Task 4: Pydantic Models — Vehicle

**Files:**
- Create: `src/tescmd/models/vehicle.py`
- Create: `tests/models/test_vehicle.py`

**Step 1: Write the failing test**

```python
# tests/models/test_vehicle.py
"""Tests for vehicle models."""

from tescmd.models.vehicle import (
    ChargeState,
    ClimateState,
    DriveState,
    Vehicle,
    VehicleData,
    VehicleState,
)


def test_vehicle_basic():
    v = Vehicle(
        vin="5YJ3E1EA1NF000000",
        display_name="My Model 3",
        state="online",
        vehicle_id=123456789,
    )
    assert v.vin == "5YJ3E1EA1NF000000"
    assert v.display_name == "My Model 3"
    assert v.state == "online"


def test_drive_state():
    ds = DriveState(
        latitude=37.3861,
        longitude=-122.0839,
        heading=180,
        speed=None,
        power=0,
        shift_state=None,
        timestamp=1706000000000,
    )
    assert ds.latitude == 37.3861
    assert ds.speed is None


def test_charge_state():
    cs = ChargeState(
        battery_level=72,
        battery_range=215.5,
        charge_limit_soc=80,
        charging_state="Disconnected",
    )
    assert cs.battery_level == 72
    assert cs.charging_state == "Disconnected"


def test_climate_state():
    cs = ClimateState(
        inside_temp=21.5,
        outside_temp=15.0,
        driver_temp_setting=22.0,
        passenger_temp_setting=22.0,
        is_climate_on=False,
    )
    assert cs.inside_temp == 21.5
    assert cs.is_climate_on is False


def test_vehicle_state():
    vs = VehicleState(
        locked=True,
        odometer=15234.5,
        sentry_mode=True,
        car_version="2025.2.6",
    )
    assert vs.locked is True
    assert vs.car_version == "2025.2.6"


def test_vehicle_data_full():
    vd = VehicleData(
        vin="5YJ3E1EA1NF000000",
        display_name="My Model 3",
        state="online",
        vehicle_id=123456789,
        charge_state=ChargeState(
            battery_level=72,
            battery_range=215.5,
            charge_limit_soc=80,
            charging_state="Disconnected",
        ),
        drive_state=DriveState(
            latitude=37.3861,
            longitude=-122.0839,
            heading=180,
            timestamp=1706000000000,
        ),
    )
    assert vd.charge_state is not None
    assert vd.charge_state.battery_level == 72
    assert vd.drive_state is not None
    assert vd.drive_state.latitude == 37.3861
    assert vd.climate_state is None


def test_vehicle_data_from_api_response():
    """Test parsing a realistic API response payload."""
    raw = {
        "vin": "5YJ3E1EA1NF000000",
        "display_name": "My Model 3",
        "state": "online",
        "vehicle_id": 123456789,
        "charge_state": {
            "battery_level": 72,
            "battery_range": 215.5,
            "charge_limit_soc": 80,
            "charging_state": "Disconnected",
            "charge_rate": 0,
            "charger_voltage": 0,
            "charger_actual_current": 0,
            "charge_port_door_open": False,
        },
        "climate_state": {
            "inside_temp": 21.5,
            "outside_temp": 15.0,
            "driver_temp_setting": 22.0,
            "passenger_temp_setting": 22.0,
            "is_climate_on": False,
            "fan_status": 0,
        },
    }
    vd = VehicleData.model_validate(raw)
    assert vd.charge_state is not None
    assert vd.charge_state.battery_level == 72
    assert vd.climate_state is not None
    assert vd.climate_state.inside_temp == 21.5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_vehicle.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/models/vehicle.py
"""Vehicle data models."""

from __future__ import annotations

from pydantic import BaseModel


class Vehicle(BaseModel):
    """Basic vehicle information from the vehicles list endpoint."""

    vin: str
    display_name: str | None = None
    state: str = "unknown"
    vehicle_id: int | None = None
    access_type: str | None = None

    model_config = {"extra": "allow"}


class DriveState(BaseModel):
    """Vehicle drive/location state."""

    latitude: float | None = None
    longitude: float | None = None
    heading: int | None = None
    speed: float | None = None
    power: int | None = None
    shift_state: str | None = None
    timestamp: int | None = None

    model_config = {"extra": "allow"}


class ChargeState(BaseModel):
    """Vehicle charge state."""

    battery_level: int | None = None
    battery_range: float | None = None
    charge_limit_soc: int | None = None
    charging_state: str | None = None
    charge_rate: float | None = None
    charger_voltage: int | None = None
    charger_actual_current: int | None = None
    charge_port_door_open: bool | None = None
    minutes_to_full_charge: int | None = None
    scheduled_charging_start_time: float | None = None
    charger_type: str | None = None

    model_config = {"extra": "allow"}


class ClimateState(BaseModel):
    """Vehicle climate state."""

    inside_temp: float | None = None
    outside_temp: float | None = None
    driver_temp_setting: float | None = None
    passenger_temp_setting: float | None = None
    is_climate_on: bool | None = None
    fan_status: int | None = None
    defrost_mode: int | None = None
    seat_heater_left: int | None = None
    seat_heater_right: int | None = None
    steering_wheel_heater: bool | None = None

    model_config = {"extra": "allow"}


class VehicleState(BaseModel):
    """Vehicle physical state (doors, locks, firmware, etc.)."""

    locked: bool | None = None
    odometer: float | None = None
    sentry_mode: bool | None = None
    car_version: str | None = None
    door_driver_front: int | None = None
    door_driver_rear: int | None = None
    door_passenger_front: int | None = None
    door_passenger_rear: int | None = None
    window_driver_front: int | None = None
    window_driver_rear: int | None = None
    window_passenger_front: int | None = None
    window_passenger_rear: int | None = None

    model_config = {"extra": "allow"}


class VehicleConfig(BaseModel):
    """Vehicle configuration (model, trim, options)."""

    car_type: str | None = None
    trim_badging: str | None = None
    exterior_color: str | None = None
    wheel_type: str | None = None

    model_config = {"extra": "allow"}


class GuiSettings(BaseModel):
    """User display preferences."""

    gui_distance_units: str | None = None
    gui_temperature_units: str | None = None
    gui_charge_rate_units: str | None = None

    model_config = {"extra": "allow"}


class VehicleData(BaseModel):
    """Full vehicle data snapshot with all state categories."""

    vin: str
    display_name: str | None = None
    state: str = "unknown"
    vehicle_id: int | None = None
    charge_state: ChargeState | None = None
    climate_state: ClimateState | None = None
    drive_state: DriveState | None = None
    vehicle_state: VehicleState | None = None
    vehicle_config: VehicleConfig | None = None
    gui_settings: GuiSettings | None = None

    model_config = {"extra": "allow"}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/models/test_vehicle.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tescmd/models/vehicle.py tests/models/test_vehicle.py
git commit -m "feat: add vehicle data models"
```

---

### Task 5: Pydantic Models — Command Response + Models Init

**Files:**
- Create: `src/tescmd/models/command.py`
- Modify: `src/tescmd/models/__init__.py`

**Step 1: Create command models**

```python
# src/tescmd/models/command.py
"""Command response models."""

from __future__ import annotations

from pydantic import BaseModel


class CommandResult(BaseModel):
    """Result from a vehicle command."""

    result: bool
    reason: str = ""


class CommandResponse(BaseModel):
    """Full response from a command endpoint."""

    response: CommandResult

    model_config = {"extra": "allow"}
```

**Step 2: Create models init with re-exports**

```python
# src/tescmd/models/__init__.py
"""Pydantic models for tescmd."""

from tescmd.models.auth import AuthConfig, TokenData, TokenMeta
from tescmd.models.command import CommandResponse, CommandResult
from tescmd.models.config import AppSettings, Profile
from tescmd.models.vehicle import (
    ChargeState,
    ClimateState,
    DriveState,
    Vehicle,
    VehicleData,
    VehicleState,
)

__all__ = [
    "AppSettings",
    "AuthConfig",
    "ChargeState",
    "ClimateState",
    "CommandResponse",
    "CommandResult",
    "DriveState",
    "Profile",
    "TokenData",
    "TokenMeta",
    "Vehicle",
    "VehicleData",
    "VehicleState",
]
```

**Step 3: Verify all model tests pass**

Run: `pytest tests/models/ -v`
Expected: all PASS

**Step 4: Commit**

```bash
git add src/tescmd/models/command.py src/tescmd/models/__init__.py
git commit -m "feat: add command models and models init re-exports"
```

---

### Task 6: Output — JSON Formatter

**Files:**
- Create: `src/tescmd/output/json_output.py`
- Create: `tests/output/test_json_output.py`

**Step 1: Write the failing test**

```python
# tests/output/test_json_output.py
"""Tests for JSON output."""

import json

from tescmd.models.vehicle import Vehicle
from tescmd.output.json_output import format_json_response, format_json_error


def test_format_success_with_model():
    vehicle = Vehicle(
        vin="5YJ3E1EA1NF000000",
        display_name="My Model 3",
        state="online",
        vehicle_id=123456789,
    )
    result = format_json_response(data=vehicle, command="vehicle.info")
    parsed = json.loads(result)

    assert parsed["ok"] is True
    assert parsed["command"] == "vehicle.info"
    assert parsed["data"]["vin"] == "5YJ3E1EA1NF000000"
    assert "timestamp" in parsed


def test_format_success_with_list():
    vehicles = [
        Vehicle(vin="VIN1", display_name="Car 1", state="online"),
        Vehicle(vin="VIN2", display_name="Car 2", state="asleep"),
    ]
    result = format_json_response(data=vehicles, command="vehicle.list")
    parsed = json.loads(result)

    assert parsed["ok"] is True
    assert len(parsed["data"]) == 2
    assert parsed["data"][0]["vin"] == "VIN1"


def test_format_success_with_dict():
    result = format_json_response(data={"result": True, "reason": ""}, command="charge.start")
    parsed = json.loads(result)

    assert parsed["ok"] is True
    assert parsed["data"]["result"] is True


def test_format_error():
    result = format_json_error(
        code="vehicle_asleep",
        message="Vehicle is asleep.",
        command="charge.start",
    )
    parsed = json.loads(result)

    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "vehicle_asleep"
    assert parsed["error"]["message"] == "Vehicle is asleep."
    assert parsed["command"] == "charge.start"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/output/test_json_output.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/output/json_output.py
"""JSON output formatting."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


def _serialize(obj: Any) -> Any:
    """Convert pydantic models and lists to JSON-serializable dicts."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(exclude_none=True)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return obj


def format_json_response(*, data: Any, command: str) -> str:
    """Format a success response as JSON."""
    envelope = {
        "ok": True,
        "command": command,
        "data": _serialize(data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(envelope, indent=2, default=str)


def format_json_error(*, code: str, message: str, command: str, **extra: Any) -> str:
    """Format an error response as JSON."""
    error_body: dict[str, Any] = {"code": code, "message": message}
    error_body.update(extra)
    envelope = {
        "ok": False,
        "command": command,
        "error": error_body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(envelope, indent=2, default=str)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/output/test_json_output.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tescmd/output/json_output.py tests/output/test_json_output.py
git commit -m "feat: add JSON output formatter"
```

---

### Task 7: Output — Rich Formatter

**Files:**
- Create: `src/tescmd/output/rich_output.py`
- Create: `tests/output/test_rich_output.py`

**Step 1: Write the failing test**

```python
# tests/output/test_rich_output.py
"""Tests for Rich output."""

from io import StringIO

from rich.console import Console

from tescmd.models.vehicle import ChargeState, DriveState, Vehicle, VehicleData
from tescmd.output.rich_output import RichOutput


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=100)
    return console, buf


def test_render_vehicle_list():
    console, buf = _make_console()
    output = RichOutput(console)
    vehicles = [
        Vehicle(vin="VIN1", display_name="Car 1", state="online", vehicle_id=111),
        Vehicle(vin="VIN2", display_name="Car 2", state="asleep", vehicle_id=222),
    ]
    output.vehicle_list(vehicles)
    text = buf.getvalue()
    assert "VIN1" in text
    assert "Car 1" in text
    assert "online" in text


def test_render_vehicle_data():
    console, buf = _make_console()
    output = RichOutput(console)
    data = VehicleData(
        vin="VIN1",
        display_name="Test Car",
        state="online",
        charge_state=ChargeState(battery_level=72, charging_state="Disconnected"),
        drive_state=DriveState(latitude=37.3861, longitude=-122.0839, heading=180),
    )
    output.vehicle_data(data)
    text = buf.getvalue()
    assert "72" in text
    assert "37.3861" in text


def test_render_location():
    console, buf = _make_console()
    output = RichOutput(console)
    drive = DriveState(latitude=37.3861, longitude=-122.0839, heading=180, speed=None)
    output.location(drive)
    text = buf.getvalue()
    assert "37.3861" in text
    assert "-122.0839" in text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/output/test_rich_output.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/output/rich_output.py
"""Rich terminal output formatting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from rich.console import Console

    from tescmd.models.vehicle import (
        ChargeState,
        ClimateState,
        DriveState,
        Vehicle,
        VehicleData,
    )


class RichOutput:
    """Rich-based output for interactive terminal sessions."""

    def __init__(self, console: Console) -> None:
        self._console = console

    def vehicle_list(self, vehicles: list[Vehicle]) -> None:
        """Display a table of vehicles."""
        table = Table(title="Vehicles")
        table.add_column("VIN", style="cyan")
        table.add_column("Name")
        table.add_column("State")
        table.add_column("ID", style="dim")

        for v in vehicles:
            state_style = "green" if v.state == "online" else "yellow"
            table.add_row(
                v.vin,
                v.display_name or "—",
                f"[{state_style}]{v.state}[/{state_style}]",
                str(v.vehicle_id or "—"),
            )

        self._console.print(table)

    def vehicle_data(self, data: VehicleData) -> None:
        """Display full vehicle data snapshot."""
        self._console.print(
            Panel(f"[bold]{data.display_name or data.vin}[/bold]  ({data.state})", expand=False)
        )

        if data.charge_state:
            self.charge_status(data.charge_state)
        if data.climate_state:
            self.climate_status(data.climate_state)
        if data.drive_state:
            self.location(data.drive_state)

    def charge_status(self, cs: ChargeState) -> None:
        """Display charge state."""
        table = Table(title="Charge", show_header=False, expand=False)
        table.add_column("Field", style="dim")
        table.add_column("Value")

        if cs.battery_level is not None:
            table.add_row("Battery", f"{cs.battery_level}%")
        if cs.battery_range is not None:
            table.add_row("Range", f"{cs.battery_range:.1f} mi")
        if cs.charging_state:
            table.add_row("Status", cs.charging_state)
        if cs.charge_limit_soc is not None:
            table.add_row("Limit", f"{cs.charge_limit_soc}%")
        if cs.charge_rate is not None and cs.charge_rate > 0:
            table.add_row("Rate", f"{cs.charge_rate} mph")
        if cs.minutes_to_full_charge is not None and cs.minutes_to_full_charge > 0:
            table.add_row("Time remaining", f"{cs.minutes_to_full_charge} min")

        self._console.print(table)

    def climate_status(self, cs: ClimateState) -> None:
        """Display climate state."""
        table = Table(title="Climate", show_header=False, expand=False)
        table.add_column("Field", style="dim")
        table.add_column("Value")

        if cs.inside_temp is not None:
            table.add_row("Inside", f"{cs.inside_temp}°C")
        if cs.outside_temp is not None:
            table.add_row("Outside", f"{cs.outside_temp}°C")
        if cs.driver_temp_setting is not None:
            table.add_row("Set (driver)", f"{cs.driver_temp_setting}°C")
        if cs.is_climate_on is not None:
            table.add_row("HVAC", "On" if cs.is_climate_on else "Off")

        self._console.print(table)

    def location(self, ds: DriveState) -> None:
        """Display vehicle location."""
        table = Table(title="Location", show_header=False, expand=False)
        table.add_column("Field", style="dim")
        table.add_column("Value")

        if ds.latitude is not None and ds.longitude is not None:
            table.add_row("Coordinates", f"{ds.latitude}, {ds.longitude}")
        if ds.heading is not None:
            table.add_row("Heading", f"{ds.heading}°")
        if ds.speed is not None:
            table.add_row("Speed", f"{ds.speed} mph")

        self._console.print(table)

    def command_result(self, success: bool, message: str = "") -> None:
        """Display a command result."""
        if success:
            self._console.print("[green]OK[/green]", message)
        else:
            self._console.print(f"[red]FAILED[/red] {message}")

    def error(self, message: str) -> None:
        """Display an error message."""
        self._console.print(f"[bold red]Error:[/bold red] {message}")

    def info(self, message: str) -> None:
        """Display an info message."""
        self._console.print(message)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/output/test_rich_output.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tescmd/output/rich_output.py tests/output/test_rich_output.py
git commit -m "feat: add Rich output formatter"
```

---

### Task 8: Output — Auto-Detecting Formatter + Output Init

**Files:**
- Create: `src/tescmd/output/formatter.py`
- Create: `tests/output/test_formatter.py`
- Modify: `src/tescmd/output/__init__.py`

**Step 1: Write the failing test**

```python
# tests/output/test_formatter.py
"""Tests for output formatter auto-detection."""

from io import StringIO
from unittest.mock import patch

from tescmd.output.formatter import OutputFormatter


def test_detect_json_when_piped():
    """Non-TTY stdout should produce JSON output."""
    buf = StringIO()
    formatter = OutputFormatter(stream=buf, force_format="json")
    assert formatter.format == "json"


def test_detect_rich_when_tty():
    """TTY stdout should produce Rich output."""
    formatter = OutputFormatter(force_format="rich")
    assert formatter.format == "rich"


def test_quiet_mode():
    formatter = OutputFormatter(force_format="quiet")
    assert formatter.format == "quiet"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/output/test_formatter.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/output/formatter.py
"""Output formatter with auto-detection."""

from __future__ import annotations

import sys
from typing import IO, Any

from pydantic import BaseModel
from rich.console import Console

from tescmd.output.json_output import format_json_error, format_json_response
from tescmd.output.rich_output import RichOutput


class OutputFormatter:
    """Routes output to the appropriate formatter based on context.

    Auto-detection: TTY → Rich, pipe → JSON, --quiet → minimal stderr.
    Can be overridden with force_format.
    """

    def __init__(
        self,
        *,
        stream: IO[str] | None = None,
        force_format: str | None = None,
    ) -> None:
        self._stream = stream or sys.stdout

        if force_format:
            self._format = force_format
        elif hasattr(self._stream, "isatty") and self._stream.isatty():
            self._format = "rich"
        else:
            self._format = "json"

        self._console = Console(file=self._stream, stderr=self._format == "quiet")
        self._rich = RichOutput(self._console)

    @property
    def format(self) -> str:
        return self._format

    @property
    def rich(self) -> RichOutput:
        return self._rich

    def output(self, data: Any, *, command: str) -> None:
        """Output data in the current format."""
        if self._format == "json":
            print(format_json_response(data=data, command=command), file=self._stream)
        elif self._format == "quiet":
            pass  # Quiet mode produces no stdout
        else:
            # Rich mode — caller should use self.rich directly for typed output
            # This is a fallback for generic data
            if isinstance(data, BaseModel):
                self._console.print(data.model_dump(exclude_none=True))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, BaseModel):
                        self._console.print(item.model_dump(exclude_none=True))
                    else:
                        self._console.print(item)
            else:
                self._console.print(data)

    def output_error(self, *, code: str, message: str, command: str) -> None:
        """Output an error in the current format."""
        if self._format == "json":
            print(
                format_json_error(code=code, message=message, command=command),
                file=self._stream,
            )
        else:
            self._rich.error(message)
```

**Step 4: Write output init**

```python
# src/tescmd/output/__init__.py
"""Output formatting for tescmd."""

from tescmd.output.formatter import OutputFormatter

__all__ = ["OutputFormatter"]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/output/test_formatter.py -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add src/tescmd/output/formatter.py src/tescmd/output/__init__.py tests/output/test_formatter.py
git commit -m "feat: add auto-detecting output formatter"
```

---

### Task 9: Internal Utilities — VIN Resolution + Async Helpers

**Files:**
- Create: `src/tescmd/_internal/async_utils.py`
- Create: `src/tescmd/_internal/vin.py`

**Step 1: Write async utils**

```python
# src/tescmd/_internal/async_utils.py
"""Asyncio utilities."""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an event loop — create a new one in a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)
```

**Step 2: Write VIN resolver**

```python
# src/tescmd/_internal/vin.py
"""Smart VIN resolution."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def resolve_vin(args: argparse.Namespace) -> str | None:
    """Resolve VIN from multiple sources in priority order.

    Resolution: positional arg > --vin flag > TESLA_VIN env > profile default > None.
    Callers should handle None by prompting interactively or raising an error.
    """
    # 1. Positional argument (e.g., tescmd vehicle info VIN123)
    vin: str | None = getattr(args, "vin_positional", None)

    # 2. --vin flag
    if not vin:
        vin = getattr(args, "vin", None)

    # 3. Environment variable (already loaded via python-dotenv)
    if not vin:
        vin = os.environ.get("TESLA_VIN")

    # 4. Profile default is handled at settings level (already in env or config)

    return vin
```

**Step 3: Commit**

```bash
git add src/tescmd/_internal/async_utils.py src/tescmd/_internal/vin.py
git commit -m "feat: add async utils and VIN resolution"
```

---

### Task 10: Run Full Phase A Checks

**Step 1: Run ruff**

```bash
ruff check src/ tests/
ruff format --check src/ tests/
```

Expected: clean (fix any issues)

**Step 2: Run mypy**

```bash
mypy src/
```

Expected: clean (fix any type errors)

**Step 3: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASS

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: phase A lint and type fixes"
```

---

## Phase B: HTTP Client + Auth

### Task 11: API Errors

**Files:**
- Create: `src/tescmd/api/errors.py`

**Step 1: Write implementation**

```python
# src/tescmd/api/errors.py
"""API error types."""

from __future__ import annotations


class TeslaAPIError(Exception):
    """Base exception for Tesla API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(TeslaAPIError):
    """Authentication or authorization failure."""


class VehicleAsleepError(TeslaAPIError):
    """Vehicle is asleep and needs to be woken."""


class VehicleNotFoundError(TeslaAPIError):
    """Vehicle not found or not accessible."""


class CommandFailedError(TeslaAPIError):
    """Vehicle rejected the command."""

    def __init__(self, message: str, reason: str = "") -> None:
        super().__init__(message)
        self.reason = reason


class RateLimitError(TeslaAPIError):
    """Rate limited by Tesla API."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class NetworkError(TeslaAPIError):
    """Network-level failure (timeout, DNS, connection refused)."""


class ConfigError(Exception):
    """Configuration error (missing client_id, invalid profile, etc.)."""
```

**Step 2: Commit**

```bash
git add src/tescmd/api/errors.py
git commit -m "feat: add typed API error hierarchy"
```

---

### Task 12: Tesla Fleet HTTP Client

**Files:**
- Create: `src/tescmd/api/client.py`
- Create: `tests/api/test_client.py`

**Step 1: Write the failing test**

```python
# tests/api/test_client.py
"""Tests for TeslaFleetClient."""

import pytest
import httpx

from tescmd.api.client import TeslaFleetClient
from tescmd.api.errors import AuthError, RateLimitError, VehicleAsleepError


FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


@pytest.fixture
def client() -> TeslaFleetClient:
    return TeslaFleetClient(access_token="test-token", region="na")


@pytest.mark.asyncio
async def test_get_success(httpx_mock, client: TeslaFleetClient):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles",
        json={"response": [{"vin": "VIN1"}], "count": 1},
    )
    result = await client.get("/api/1/vehicles")
    assert result["response"][0]["vin"] == "VIN1"


@pytest.mark.asyncio
async def test_post_success(httpx_mock, client: TeslaFleetClient):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles/VIN1/command/charge_start",
        json={"response": {"result": True, "reason": ""}},
    )
    result = await client.post("/api/1/vehicles/VIN1/command/charge_start")
    assert result["response"]["result"] is True


@pytest.mark.asyncio
async def test_auth_header_sent(httpx_mock, client: TeslaFleetClient):
    httpx_mock.add_response(url=f"{FLEET_BASE}/api/1/vehicles", json={"response": []})
    await client.get("/api/1/vehicles")
    request = httpx_mock.get_requests()[0]
    assert request.headers["authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_rate_limit_raises(httpx_mock, client: TeslaFleetClient):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles",
        status_code=429,
        headers={"retry-after": "30"},
        json={"error": "rate_limited"},
    )
    with pytest.raises(RateLimitError) as exc_info:
        await client.get("/api/1/vehicles")
    assert exc_info.value.retry_after == 30


@pytest.mark.asyncio
async def test_vehicle_asleep_raises(httpx_mock, client: TeslaFleetClient):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles/VIN1/vehicle_data",
        status_code=408,
        json={"error": "vehicle unavailable: vehicle is offline or asleep"},
    )
    with pytest.raises(VehicleAsleepError):
        await client.get("/api/1/vehicles/VIN1/vehicle_data")


@pytest.mark.asyncio
async def test_region_base_url():
    eu_client = TeslaFleetClient(access_token="test", region="eu")
    assert "eu" in eu_client.base_url
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_client.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/api/client.py
"""Tesla Fleet API HTTP client."""

from __future__ import annotations

from typing import Any

import httpx

from tescmd.api.errors import (
    AuthError,
    NetworkError,
    RateLimitError,
    TeslaAPIError,
    VehicleAsleepError,
)

REGION_BASE_URLS = {
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.com",
}


class TeslaFleetClient:
    """Async HTTP client for the Tesla Fleet API.

    Handles auth headers, regional base URLs, and error mapping.
    Token refresh is delegated to a callback (set by the auth layer).
    """

    def __init__(
        self,
        *,
        access_token: str,
        region: str = "na",
        timeout: float = 30.0,
        on_token_refresh: Any | None = None,
    ) -> None:
        self.base_url = REGION_BASE_URLS.get(region, REGION_BASE_URLS["na"])
        self._access_token = access_token
        self._on_token_refresh = on_token_refresh
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._auth_headers(),
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def update_token(self, access_token: str) -> None:
        """Update the access token (after refresh)."""
        self._access_token = access_token
        self._http.headers.update(self._auth_headers())

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a GET request."""
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Send a POST request."""
        return await self._request("POST", path, **kwargs)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Execute an HTTP request with error handling."""
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as e:
            raise NetworkError(f"Request timed out: {e}") from e
        except httpx.ConnectError as e:
            raise NetworkError(f"Connection failed: {e}") from e

        if response.status_code == 401:
            # Try token refresh if callback is set
            if self._on_token_refresh:
                new_token = await self._on_token_refresh()
                if new_token:
                    self.update_token(new_token)
                    # Retry once with new token
                    response = await self._http.request(method, path, **kwargs)
                    if response.status_code == 401:
                        raise AuthError("Authentication failed after token refresh", 401)
                    return self._parse_response(response)
            raise AuthError("Authentication failed. Run: tescmd auth login", 401)

        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse response and raise typed errors for failure status codes."""
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitError(
                "Rate limited by Tesla API",
                retry_after=int(retry_after) if retry_after else None,
            )

        if response.status_code == 408:
            raise VehicleAsleepError("Vehicle is asleep or offline", 408)

        if response.status_code >= 400:
            try:
                body = response.json()
                msg = body.get("error", response.text)
            except Exception:
                msg = response.text
            raise TeslaAPIError(f"API error ({response.status_code}): {msg}", response.status_code)

        result: dict[str, Any] = response.json()
        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> TeslaFleetClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
```

**Step 4: Update api init**

```python
# src/tescmd/api/__init__.py
"""Tesla Fleet API client layer."""
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/api/test_client.py -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add src/tescmd/api/client.py src/tescmd/api/__init__.py tests/api/test_client.py
git commit -m "feat: add Tesla Fleet HTTP client with error handling"
```

---

### Task 13: Auth — Token Store (Keyring)

**Files:**
- Create: `src/tescmd/auth/token_store.py`
- Create: `tests/auth/test_token_store.py`

**Step 1: Write the failing test**

```python
# tests/auth/test_token_store.py
"""Tests for token store."""

import json
from unittest.mock import MagicMock, patch

import pytest

from tescmd.auth.token_store import TokenStore


@pytest.fixture
def mock_keyring():
    """Mock keyring module."""
    store = {}

    def get_password(service: str, username: str) -> str | None:
        return store.get(f"{service}:{username}")

    def set_password(service: str, username: str, password: str) -> None:
        store[f"{service}:{username}"] = password

    def delete_password(service: str, username: str) -> None:
        store.pop(f"{service}:{username}", None)

    with patch("tescmd.auth.token_store.keyring") as mock:
        mock.get_password = MagicMock(side_effect=get_password)
        mock.set_password = MagicMock(side_effect=set_password)
        mock.delete_password = MagicMock(side_effect=delete_password)
        mock._store = store  # expose for assertions
        yield mock


def test_save_and_load_tokens(mock_keyring):
    store = TokenStore(profile="default")
    store.save(
        access_token="access_123",
        refresh_token="refresh_456",
        expires_at=1700000000.0,
        scopes=["openid", "vehicle_device_data"],
        region="na",
    )

    assert store.access_token == "access_123"
    assert store.refresh_token == "refresh_456"


def test_load_missing_token(mock_keyring):
    store = TokenStore(profile="default")
    assert store.access_token is None
    assert store.refresh_token is None


def test_clear_tokens(mock_keyring):
    store = TokenStore(profile="default")
    store.save(
        access_token="access_123",
        refresh_token="refresh_456",
        expires_at=1700000000.0,
        scopes=["openid"],
        region="na",
    )
    store.clear()
    assert store.access_token is None


def test_has_token(mock_keyring):
    store = TokenStore(profile="default")
    assert store.has_token is False

    store.save(
        access_token="access_123",
        refresh_token=None,
        expires_at=1700000000.0,
        scopes=[],
        region="na",
    )
    assert store.has_token is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/auth/test_token_store.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/auth/token_store.py
"""Keyring-backed token storage."""

from __future__ import annotations

import json
from typing import Any

import keyring

SERVICE_NAME = "tescmd"


class TokenStore:
    """Stores OAuth tokens in the OS keyring.

    Each profile gets its own set of keyring entries:
      service: tescmd
      username: {profile}/access_token
      username: {profile}/refresh_token
      username: {profile}/token_meta  (JSON: expires_at, scopes, region)
    """

    def __init__(self, profile: str = "default") -> None:
        self._profile = profile

    def _key(self, name: str) -> str:
        return f"{self._profile}/{name}"

    @property
    def access_token(self) -> str | None:
        return keyring.get_password(SERVICE_NAME, self._key("access_token"))

    @property
    def refresh_token(self) -> str | None:
        return keyring.get_password(SERVICE_NAME, self._key("refresh_token"))

    @property
    def has_token(self) -> bool:
        return self.access_token is not None

    @property
    def metadata(self) -> dict[str, Any] | None:
        raw = keyring.get_password(SERVICE_NAME, self._key("token_meta"))
        if raw:
            result: dict[str, Any] = json.loads(raw)
            return result
        return None

    def save(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        expires_at: float,
        scopes: list[str],
        region: str,
    ) -> None:
        """Save tokens and metadata to keyring."""
        keyring.set_password(SERVICE_NAME, self._key("access_token"), access_token)
        if refresh_token:
            keyring.set_password(SERVICE_NAME, self._key("refresh_token"), refresh_token)

        meta = json.dumps({"expires_at": expires_at, "scopes": scopes, "region": region})
        keyring.set_password(SERVICE_NAME, self._key("token_meta"), meta)

    def clear(self) -> None:
        """Remove all tokens for this profile."""
        for name in ("access_token", "refresh_token", "token_meta"):
            try:
                keyring.delete_password(SERVICE_NAME, self._key(name))
            except keyring.errors.PasswordDeleteError:
                pass

    def export_dict(self) -> dict[str, Any]:
        """Export tokens as a dict (for auth export command)."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "metadata": self.metadata,
        }

    def import_dict(self, data: dict[str, Any]) -> None:
        """Import tokens from a dict (for auth import command)."""
        meta = data.get("metadata", {})
        self.save(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=meta.get("expires_at", 0),
            scopes=meta.get("scopes", []),
            region=meta.get("region", "na"),
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/auth/test_token_store.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tescmd/auth/token_store.py tests/auth/test_token_store.py
git commit -m "feat: add keyring-backed token store"
```

---

### Task 14: Auth — OAuth2 PKCE Flow + Callback Server

**Files:**
- Create: `src/tescmd/auth/server.py`
- Create: `src/tescmd/auth/oauth.py`
- Create: `src/tescmd/auth/__init__.py`
- Create: `tests/auth/test_oauth.py`

**Step 1: Write the callback server**

```python
# src/tescmd/auth/server.py
"""Local HTTP server for OAuth2 callback."""

from __future__ import annotations

import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from threading import Thread
from typing import Any


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth redirect callback."""

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "error" in params:
            _CallbackHandler.error = params["error"][0]
        elif "code" in params:
            _CallbackHandler.code = params["code"][0]
            _CallbackHandler.state = params.get("state", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if _CallbackHandler.error:
            body = "<h1>Authentication Failed</h1><p>You can close this window.</p>"
        else:
            body = "<h1>Authentication Successful</h1><p>You can close this window and return to the terminal.</p>"

        self.wfile.write(body.encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default logging


class OAuthCallbackServer:
    """Runs a temporary local server to receive the OAuth redirect."""

    def __init__(self, port: int = 8085) -> None:
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start the callback server in a background thread."""
        _CallbackHandler.code = None
        _CallbackHandler.state = None
        _CallbackHandler.error = None

        self._server = HTTPServer(("localhost", self.port), _CallbackHandler)
        self._thread = Thread(target=self._server.handle_request, daemon=True)
        self._thread.start()

    def wait_for_callback(self, timeout: float = 120.0) -> tuple[str | None, str | None]:
        """Wait for the callback and return (code, state) or (None, error)."""
        if self._thread:
            self._thread.join(timeout=timeout)

        if _CallbackHandler.error:
            return None, _CallbackHandler.error

        return _CallbackHandler.code, _CallbackHandler.state

    def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.server_close()
```

**Step 2: Write the OAuth flow**

```python
# src/tescmd/auth/oauth.py
"""OAuth2 PKCE authentication flow."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import webbrowser
from typing import Any
from urllib.parse import urlencode

import httpx

from tescmd.api.errors import AuthError
from tescmd.auth.server import OAuthCallbackServer
from tescmd.auth.token_store import TokenStore
from tescmd.models.auth import (
    AUTH_BASE_URL,
    AUTHORIZE_URL,
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPES,
    TOKEN_URL,
    TokenData,
)


def _generate_code_verifier() -> str:
    """Generate a PKCE code verifier (128 random bytes, base64url-encoded)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(96)).rstrip(b"=").decode("ascii")


def _generate_code_challenge(verifier: str) -> str:
    """Derive a PKCE code challenge from the verifier (S256)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_auth_url(
    *,
    client_id: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scopes: list[str] = DEFAULT_SCOPES,
    code_challenge: str,
    state: str,
) -> str:
    """Build the Tesla authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(
    *,
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> TokenData:
    """Exchange an authorization code for tokens."""
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient() as http:
        response = await http.post(TOKEN_URL, data=payload)

    if response.status_code != 200:
        raise AuthError(f"Token exchange failed ({response.status_code}): {response.text}")

    return TokenData.model_validate(response.json())


async def refresh_access_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str | None = None,
) -> TokenData:
    """Refresh an access token using a refresh token."""
    payload: dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient() as http:
        response = await http.post(TOKEN_URL, data=payload)

    if response.status_code != 200:
        raise AuthError(f"Token refresh failed ({response.status_code}): {response.text}")

    return TokenData.model_validate(response.json())


async def login_flow(
    *,
    client_id: str,
    client_secret: str | None = None,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scopes: list[str] = DEFAULT_SCOPES,
    port: int = 8085,
    token_store: TokenStore,
    region: str = "na",
) -> TokenData:
    """Run the full interactive OAuth2 PKCE login flow.

    1. Generate PKCE verifier + challenge
    2. Start local callback server
    3. Open browser to Tesla auth page
    4. Wait for redirect with auth code
    5. Exchange code for tokens
    6. Store tokens in keyring
    """
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)
    state = secrets.token_urlsafe(32)

    auth_url = build_auth_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        scopes=scopes,
        code_challenge=code_challenge,
        state=state,
    )

    server = OAuthCallbackServer(port=port)
    server.start()

    webbrowser.open(auth_url)

    code, callback_state = server.wait_for_callback(timeout=120.0)
    server.stop()

    if not code:
        raise AuthError(f"Authentication failed: {callback_state or 'no code received'}")

    if callback_state != state:
        raise AuthError("State mismatch — possible CSRF attack")

    token_data = await exchange_code(
        code=code,
        code_verifier=code_verifier,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )

    token_store.save(
        access_token=token_data.access_token,
        refresh_token=token_data.refresh_token,
        expires_at=time.time() + token_data.expires_in,
        scopes=scopes,
        region=region,
    )

    return token_data
```

**Step 3: Update auth init**

```python
# src/tescmd/auth/__init__.py
"""Authentication for tescmd."""
```

**Step 4: Write tests for PKCE and URL building (no browser/server needed)**

```python
# tests/auth/test_oauth.py
"""Tests for OAuth2 flow helpers."""

import pytest

from tescmd.auth.oauth import (
    _generate_code_challenge,
    _generate_code_verifier,
    build_auth_url,
)


def test_code_verifier_length():
    verifier = _generate_code_verifier()
    # 96 bytes → 128 base64url chars (no padding)
    assert len(verifier) == 128


def test_code_verifier_unique():
    v1 = _generate_code_verifier()
    v2 = _generate_code_verifier()
    assert v1 != v2


def test_code_challenge_is_sha256():
    verifier = _generate_code_verifier()
    challenge = _generate_code_challenge(verifier)
    # SHA-256 → 32 bytes → 43 base64url chars (no padding)
    assert len(challenge) == 43


def test_build_auth_url():
    url = build_auth_url(
        client_id="test-client",
        redirect_uri="http://localhost:8085/callback",
        scopes=["openid", "vehicle_device_data"],
        code_challenge="test_challenge_abc",
        state="test_state_xyz",
    )
    assert "client_id=test-client" in url
    assert "response_type=code" in url
    assert "code_challenge=test_challenge_abc" in url
    assert "code_challenge_method=S256" in url
    assert "state=test_state_xyz" in url
    assert "openid" in url
```

**Step 5: Run tests**

Run: `pytest tests/auth/ -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add src/tescmd/auth/ tests/auth/
git commit -m "feat: add OAuth2 PKCE flow, callback server, token store"
```

---

### Task 15: CLI — Main Parser + Auth Commands

**Files:**
- Create: `src/tescmd/cli/main.py`
- Create: `src/tescmd/cli/auth.py`

**Step 1: Write CLI main**

```python
# src/tescmd/cli/main.py
"""CLI entry point and root argument parser."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from tescmd._internal.async_utils import run_async
from tescmd.output.formatter import OutputFormatter


def build_parser() -> argparse.ArgumentParser:
    """Build the root argument parser."""
    parser = argparse.ArgumentParser(
        prog="tescmd",
        description="Query and control Tesla vehicles via the Fleet API.",
    )
    parser.add_argument("--vin", help="Vehicle Identification Number")
    parser.add_argument(
        "--profile", default="default", help="Config profile name (default: default)"
    )
    parser.add_argument(
        "--format",
        choices=["rich", "json", "quiet"],
        dest="output_format",
        help="Output format (default: auto-detect)",
    )
    parser.add_argument("--quiet", action="store_true", help="Minimal output (exit codes only)")
    parser.add_argument(
        "--region", choices=["na", "eu", "cn"], help="API region (default: from profile)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Command group")

    # Register command groups
    from tescmd.cli import auth as auth_cli
    from tescmd.cli import vehicle as vehicle_cli

    auth_cli.register(subparsers)
    vehicle_cli.register(subparsers)

    return parser


def main(argv: list[str] | None = None) -> NoReturn:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Resolve output format
    fmt = "quiet" if args.quiet else args.output_format
    formatter = OutputFormatter(force_format=fmt)

    # Dispatch to command handler
    if hasattr(args, "func"):
        try:
            exit_code = run_async(args.func(args, formatter))
        except KeyboardInterrupt:
            sys.exit(130)
        except Exception as e:
            formatter.output_error(code="error", message=str(e), command=args.command)
            sys.exit(1)
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(0)
```

**Step 2: Write auth CLI**

```python
# src/tescmd/cli/auth.py
"""CLI commands for authentication."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import TYPE_CHECKING

from tescmd.api.errors import AuthError, ConfigError
from tescmd.auth.oauth import login_flow, refresh_access_token
from tescmd.auth.token_store import TokenStore
from tescmd.models.auth import DEFAULT_REDIRECT_URI, DEFAULT_SCOPES
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    from tescmd.output.formatter import OutputFormatter


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register auth commands."""
    parser = subparsers.add_parser("auth", help="OAuth2 authentication")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # auth login
    login_parser = sub.add_parser("login", help="Authenticate via browser")
    login_parser.add_argument("--port", type=int, default=8085, help="Callback server port")
    login_parser.set_defaults(func=cmd_login)

    # auth logout
    logout_parser = sub.add_parser("logout", help="Remove stored tokens")
    logout_parser.set_defaults(func=cmd_logout)

    # auth status
    status_parser = sub.add_parser("status", help="Show authentication status")
    status_parser.set_defaults(func=cmd_status)

    # auth refresh
    refresh_parser = sub.add_parser("refresh", help="Manually refresh access token")
    refresh_parser.set_defaults(func=cmd_refresh)

    # auth export
    export_parser = sub.add_parser("export", help="Export tokens as JSON")
    export_parser.set_defaults(func=cmd_export)

    # auth import
    import_parser = sub.add_parser("import", help="Import tokens from JSON")
    import_parser.set_defaults(func=cmd_import)


async def cmd_login(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Run the interactive login flow."""
    settings = AppSettings()

    if not settings.tesla_client_id:
        raise ConfigError(
            "TESLA_CLIENT_ID is required. Set it in .env or environment variables.\n"
            "Get your client ID at: https://developer.tesla.com"
        )

    store = TokenStore(profile=args.profile)
    region = args.region or settings.tesla_region

    formatter.rich.info("Starting OAuth2 login flow...")
    formatter.rich.info("A browser window will open for Tesla authentication.")

    token_data = await login_flow(
        client_id=settings.tesla_client_id,
        client_secret=settings.tesla_client_secret,
        port=args.port,
        token_store=store,
        region=region,
    )

    formatter.rich.info("[green]Authentication successful![/green]")
    formatter.rich.info(f"Token expires in {token_data.expires_in // 3600} hours.")
    return 0


async def cmd_logout(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Remove stored tokens."""
    store = TokenStore(profile=args.profile)
    store.clear()
    formatter.rich.info(f"Tokens cleared for profile '{args.profile}'.")
    return 0


async def cmd_status(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Show authentication status."""
    store = TokenStore(profile=args.profile)

    if not store.has_token:
        formatter.rich.info("Not authenticated. Run: tescmd auth login")
        return 2

    meta = store.metadata
    if meta:
        expires_at = meta.get("expires_at", 0)
        remaining = expires_at - time.time()
        scopes = meta.get("scopes", [])
        region = meta.get("region", "unknown")

        if formatter.format == "json":
            formatter.output(
                {
                    "authenticated": True,
                    "profile": args.profile,
                    "region": region,
                    "scopes": scopes,
                    "expires_in_seconds": max(0, int(remaining)),
                    "has_refresh_token": store.refresh_token is not None,
                },
                command="auth.status",
            )
        else:
            formatter.rich.info(f"Profile: {args.profile}")
            formatter.rich.info(f"Region: {region}")
            formatter.rich.info(f"Scopes: {', '.join(scopes)}")
            if remaining > 0:
                hours = int(remaining // 3600)
                minutes = int((remaining % 3600) // 60)
                formatter.rich.info(f"Token expires in: {hours}h {minutes}m")
            else:
                formatter.rich.info("[yellow]Token expired. Run: tescmd auth refresh[/yellow]")
            formatter.rich.info(
                f"Refresh token: {'available' if store.refresh_token else 'not available'}"
            )
    else:
        formatter.rich.info("Authenticated (no metadata available).")

    return 0


async def cmd_refresh(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Manually refresh the access token."""
    settings = AppSettings()
    store = TokenStore(profile=args.profile)

    if not store.refresh_token:
        raise AuthError("No refresh token available. Run: tescmd auth login")

    if not settings.tesla_client_id:
        raise ConfigError("TESLA_CLIENT_ID is required for token refresh.")

    token_data = await refresh_access_token(
        refresh_token=store.refresh_token,
        client_id=settings.tesla_client_id,
        client_secret=settings.tesla_client_secret,
    )

    region = "na"
    meta = store.metadata
    if meta:
        region = meta.get("region", "na")

    store.save(
        access_token=token_data.access_token,
        refresh_token=token_data.refresh_token or store.refresh_token,
        expires_at=time.time() + token_data.expires_in,
        scopes=meta.get("scopes", []) if meta else [],
        region=region,
    )

    formatter.rich.info("[green]Token refreshed successfully.[/green]")
    return 0


async def cmd_export(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Export tokens as JSON to stdout."""
    store = TokenStore(profile=args.profile)
    if not store.has_token:
        raise AuthError("No tokens to export. Run: tescmd auth login")

    data = store.export_dict()
    print(json.dumps(data, indent=2))
    return 0


async def cmd_import(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Import tokens from JSON on stdin."""
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON input: {e}") from e

    if "access_token" not in data:
        raise ConfigError("JSON must contain 'access_token' field.")

    store = TokenStore(profile=args.profile)
    store.import_dict(data)
    formatter.rich.info(f"Tokens imported for profile '{args.profile}'.")
    return 0
```

**Step 3: Verify entry point works**

```bash
python -m tescmd --help
python -m tescmd auth --help
```

Expected: help text displays with auth subcommands.

**Step 4: Commit**

```bash
git add src/tescmd/cli/main.py src/tescmd/cli/auth.py
git commit -m "feat: add CLI main parser and auth commands"
```

---

## Phase C: Vehicle Data + CLI

### Task 16: Vehicle API

**Files:**
- Create: `src/tescmd/api/vehicle.py`
- Create: `tests/api/test_vehicle_api.py`

**Step 1: Write the failing test**

```python
# tests/api/test_vehicle_api.py
"""Tests for VehicleAPI."""

import pytest

from tescmd.api.client import TeslaFleetClient
from tescmd.api.vehicle import VehicleAPI


FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


@pytest.fixture
def client() -> TeslaFleetClient:
    return TeslaFleetClient(access_token="test-token", region="na")


@pytest.fixture
def vehicle_api(client: TeslaFleetClient) -> VehicleAPI:
    return VehicleAPI(client)


@pytest.mark.asyncio
async def test_list_vehicles(httpx_mock, vehicle_api: VehicleAPI):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles",
        json={
            "response": [
                {"vin": "VIN1", "display_name": "Car 1", "state": "online", "vehicle_id": 111},
                {"vin": "VIN2", "display_name": "Car 2", "state": "asleep", "vehicle_id": 222},
            ],
            "count": 2,
        },
    )
    vehicles = await vehicle_api.list()
    assert len(vehicles) == 2
    assert vehicles[0].vin == "VIN1"
    assert vehicles[1].state == "asleep"


@pytest.mark.asyncio
async def test_get_vehicle_data(httpx_mock, vehicle_api: VehicleAPI):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles/VIN1/vehicle_data",
        json={
            "response": {
                "vin": "VIN1",
                "display_name": "Car 1",
                "state": "online",
                "vehicle_id": 111,
                "charge_state": {"battery_level": 72, "charging_state": "Disconnected"},
                "drive_state": {"latitude": 37.3861, "longitude": -122.0839},
            }
        },
    )
    data = await vehicle_api.get_vehicle_data("VIN1")
    assert data.vin == "VIN1"
    assert data.charge_state is not None
    assert data.charge_state.battery_level == 72


@pytest.mark.asyncio
async def test_get_vehicle_data_with_endpoints(httpx_mock, vehicle_api: VehicleAPI):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles/VIN1/vehicle_data?endpoints=charge_state%3Bdrive_state",
        json={
            "response": {
                "vin": "VIN1",
                "charge_state": {"battery_level": 50},
                "drive_state": {"latitude": 40.0},
            }
        },
    )
    data = await vehicle_api.get_vehicle_data("VIN1", endpoints=["charge_state", "drive_state"])
    assert data.charge_state is not None
    assert data.charge_state.battery_level == 50


@pytest.mark.asyncio
async def test_wake_vehicle(httpx_mock, vehicle_api: VehicleAPI):
    httpx_mock.add_response(
        url=f"{FLEET_BASE}/api/1/vehicles/VIN1/wake_up",
        json={"response": {"vin": "VIN1", "state": "online"}},
    )
    vehicle = await vehicle_api.wake("VIN1")
    assert vehicle.state == "online"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_vehicle_api.py -v`
Expected: FAIL — ModuleNotFoundError

**Step 3: Write implementation**

```python
# src/tescmd/api/vehicle.py
"""Vehicle API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tescmd.models.vehicle import Vehicle, VehicleData

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class VehicleAPI:
    """Tesla Fleet API vehicle endpoints.

    Handles vehicle listing, data queries, and wake. Uses composition —
    wraps a TeslaFleetClient instance rather than inheriting.
    """

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def list(self) -> list[Vehicle]:
        """List all vehicles on the account."""
        response = await self._client.get("/api/1/vehicles")
        return [Vehicle.model_validate(v) for v in response["response"]]

    async def get_vehicle_data(
        self,
        vin: str,
        *,
        endpoints: list[str] | None = None,
    ) -> VehicleData:
        """Get vehicle data snapshot.

        Args:
            vin: Vehicle Identification Number.
            endpoints: Optional list of data categories to request
                       (charge_state, climate_state, drive_state, vehicle_state,
                       vehicle_config, gui_settings).
        """
        path = f"/api/1/vehicles/{vin}/vehicle_data"
        params = {}
        if endpoints:
            params["endpoints"] = ";".join(endpoints)

        response = await self._client.get(path, params=params)
        return VehicleData.model_validate(response["response"])

    async def wake(self, vin: str) -> Vehicle:
        """Wake a sleeping vehicle."""
        response = await self._client.post(f"/api/1/vehicles/{vin}/wake_up")
        return Vehicle.model_validate(response["response"])
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_vehicle_api.py -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add src/tescmd/api/vehicle.py tests/api/test_vehicle_api.py
git commit -m "feat: add VehicleAPI (list, data, wake)"
```

---

### Task 17: CLI — Vehicle Commands

**Files:**
- Create: `src/tescmd/cli/vehicle.py`

**Step 1: Write implementation**

```python
# src/tescmd/cli/vehicle.py
"""CLI commands for vehicle information."""

from __future__ import annotations

import argparse
import asyncio
from typing import TYPE_CHECKING

from tescmd._internal.vin import resolve_vin
from tescmd.api.client import TeslaFleetClient
from tescmd.api.errors import ConfigError, VehicleAsleepError
from tescmd.api.vehicle import VehicleAPI
from tescmd.auth.token_store import TokenStore
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    from tescmd.output.formatter import OutputFormatter


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register vehicle commands."""
    parser = subparsers.add_parser("vehicle", help="Vehicle information and status")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # vehicle list
    list_parser = sub.add_parser("list", help="List all vehicles")
    list_parser.set_defaults(func=cmd_list)

    # vehicle info [VIN]
    info_parser = sub.add_parser("info", help="Get vehicle summary")
    info_parser.add_argument("vin_positional", nargs="?", help="Vehicle VIN")
    info_parser.set_defaults(func=cmd_info)

    # vehicle data [VIN]
    data_parser = sub.add_parser("data", help="Get full vehicle data")
    data_parser.add_argument("vin_positional", nargs="?", help="Vehicle VIN")
    data_parser.add_argument("--endpoints", help="Comma-separated data categories")
    data_parser.set_defaults(func=cmd_data)

    # vehicle location [VIN]
    loc_parser = sub.add_parser("location", help="Get vehicle location")
    loc_parser.add_argument("vin_positional", nargs="?", help="Vehicle VIN")
    loc_parser.set_defaults(func=cmd_location)

    # vehicle wake [VIN]
    wake_parser = sub.add_parser("wake", help="Wake a sleeping vehicle")
    wake_parser.add_argument("vin_positional", nargs="?", help="Vehicle VIN")
    wake_parser.add_argument("--wait", action="store_true", help="Block until online")
    wake_parser.add_argument("--timeout", type=int, default=30, help="Wait timeout in seconds")
    wake_parser.set_defaults(func=cmd_wake)


def _get_client_and_api(args: argparse.Namespace) -> tuple[TeslaFleetClient, VehicleAPI]:
    """Create the API client from current settings and tokens."""
    settings = AppSettings()

    # Check for direct token in env
    access_token = settings.tesla_access_token

    if not access_token:
        store = TokenStore(profile=args.profile)
        access_token = store.access_token

    if not access_token:
        raise ConfigError("Not authenticated. Run: tescmd auth login")

    region = args.region or settings.tesla_region
    client = TeslaFleetClient(access_token=access_token, region=region)
    api = VehicleAPI(client)
    return client, api


def _require_vin(args: argparse.Namespace) -> str:
    """Resolve VIN or raise an error."""
    vin = resolve_vin(args)
    if not vin:
        raise ConfigError(
            "No VIN specified. Use positional arg, --vin flag, or set TESLA_VIN.\n"
            "List your vehicles: tescmd vehicle list"
        )
    return vin


async def cmd_list(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """List all vehicles."""
    client, api = _get_client_and_api(args)
    async with client:
        vehicles = await api.list()

    if formatter.format == "json":
        formatter.output(vehicles, command="vehicle.list")
    else:
        formatter.rich.vehicle_list(vehicles)
    return 0


async def cmd_info(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Get vehicle summary."""
    vin = _require_vin(args)
    client, api = _get_client_and_api(args)
    async with client:
        data = await api.get_vehicle_data(vin)

    if formatter.format == "json":
        formatter.output(data, command="vehicle.info")
    else:
        formatter.rich.vehicle_data(data)
    return 0


async def cmd_data(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Get full vehicle data."""
    vin = _require_vin(args)
    client, api = _get_client_and_api(args)

    endpoints = None
    if args.endpoints:
        endpoints = [e.strip() for e in args.endpoints.split(",")]

    async with client:
        data = await api.get_vehicle_data(vin, endpoints=endpoints)

    if formatter.format == "json":
        formatter.output(data, command="vehicle.data")
    else:
        formatter.rich.vehicle_data(data)
    return 0


async def cmd_location(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Get vehicle location."""
    vin = _require_vin(args)
    client, api = _get_client_and_api(args)
    async with client:
        data = await api.get_vehicle_data(vin, endpoints=["drive_state"])

    if formatter.format == "json":
        formatter.output(data.drive_state, command="vehicle.location")
    elif data.drive_state:
        formatter.rich.location(data.drive_state)
    else:
        formatter.rich.info("No location data available.")
    return 0


async def cmd_wake(args: argparse.Namespace, formatter: OutputFormatter) -> int:
    """Wake a sleeping vehicle."""
    vin = _require_vin(args)
    client, api = _get_client_and_api(args)

    async with client:
        vehicle = await api.wake(vin)

        if args.wait and vehicle.state != "online":
            timeout = args.timeout
            elapsed = 0
            while vehicle.state != "online" and elapsed < timeout:
                await asyncio.sleep(2)
                elapsed += 2
                try:
                    vehicle = await api.wake(vin)
                except VehicleAsleepError:
                    continue

            if vehicle.state != "online":
                formatter.output_error(
                    code="timeout",
                    message=f"Vehicle did not wake within {timeout}s",
                    command="vehicle.wake",
                )
                return 3

    if formatter.format == "json":
        formatter.output(vehicle, command="vehicle.wake")
    else:
        style = "green" if vehicle.state == "online" else "yellow"
        formatter.rich.info(f"Vehicle state: [{style}]{vehicle.state}[/{style}]")
    return 0
```

**Step 2: Verify CLI help works**

```bash
python -m tescmd vehicle --help
python -m tescmd vehicle list --help
python -m tescmd vehicle location --help
```

Expected: help text for each subcommand.

**Step 3: Commit**

```bash
git add src/tescmd/cli/vehicle.py
git commit -m "feat: add vehicle CLI commands (list, info, data, location, wake)"
```

---

### Task 18: Shared Test Fixtures

**Files:**
- Create: `tests/conftest.py`

**Step 1: Write conftest**

```python
# tests/conftest.py
"""Shared test fixtures."""

import pytest

from tescmd.api.client import TeslaFleetClient


FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


@pytest.fixture
def fleet_base() -> str:
    return FLEET_BASE


@pytest.fixture
def mock_client() -> TeslaFleetClient:
    """Pre-configured client for testing."""
    return TeslaFleetClient(access_token="test-token", region="na")


@pytest.fixture
def sample_vehicle_list_response() -> dict:
    return {
        "response": [
            {
                "vin": "5YJ3E1EA1NF000000",
                "display_name": "My Model 3",
                "state": "online",
                "vehicle_id": 123456789,
            }
        ],
        "count": 1,
    }


@pytest.fixture
def sample_vehicle_data_response() -> dict:
    return {
        "response": {
            "vin": "5YJ3E1EA1NF000000",
            "display_name": "My Model 3",
            "state": "online",
            "vehicle_id": 123456789,
            "charge_state": {
                "battery_level": 72,
                "battery_range": 215.5,
                "charge_limit_soc": 80,
                "charging_state": "Disconnected",
            },
            "climate_state": {
                "inside_temp": 21.5,
                "outside_temp": 15.0,
                "driver_temp_setting": 22.0,
                "passenger_temp_setting": 22.0,
                "is_climate_on": False,
            },
            "drive_state": {
                "latitude": 37.3861,
                "longitude": -122.0839,
                "heading": 180,
                "speed": None,
                "power": 0,
                "timestamp": 1706000000000,
            },
            "vehicle_state": {
                "locked": True,
                "odometer": 15234.5,
                "sentry_mode": True,
                "car_version": "2025.2.6",
            },
        }
    }
```

**Step 2: Commit**

```bash
git add tests/conftest.py
git commit -m "feat: add shared test fixtures"
```

---

### Task 19: Final Checks + MVP Verification

**Step 1: Run ruff**

```bash
ruff check src/ tests/
ruff format src/ tests/
```

Fix any issues.

**Step 2: Run mypy**

```bash
mypy src/
```

Fix any type errors.

**Step 3: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASS.

**Step 4: Verify CLI end-to-end (help only, no API)**

```bash
python -m tescmd --help
python -m tescmd auth --help
python -m tescmd auth login --help
python -m tescmd vehicle --help
python -m tescmd vehicle list --help
python -m tescmd vehicle location --help
```

Expected: all help text renders correctly.

**Step 5: Verify entry point**

```bash
tescmd --help
```

Expected: same output as `python -m tescmd --help`.

**Step 6: Commit any fixes and tag MVP**

```bash
git add -A
git commit -m "fix: final lint and type fixes for MVP"
git tag -a v0.1.0-alpha -m "MVP: auth + vehicle data"
```
