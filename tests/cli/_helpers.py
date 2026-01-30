"""Helpers for CLI execution tests."""

from __future__ import annotations

import json
from typing import Any

from click.testing import CliRunner

from tescmd.cli.main import cli

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"


def invoke_json(args: list[str], **kwargs: Any) -> dict[str, Any]:
    """Invoke CLI with --format json and parse output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--format", "json", *args], catch_exceptions=False, **kwargs)
    assert result.exit_code == 0, f"CLI failed (exit {result.exit_code}): {result.output}"
    return json.loads(result.output)


def invoke_cli(args: list[str], **kwargs: Any) -> Any:
    """Invoke CLI and return the Click Result object."""
    runner = CliRunner()
    return runner.invoke(cli, args, catch_exceptions=False, **kwargs)
