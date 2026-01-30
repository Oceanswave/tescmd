"""Debug script to see charge limit CLI output."""

import os

os.environ["TESLA_ACCESS_TOKEN"] = "test"
os.environ["TESLA_VIN"] = "5YJ3E1EA1NF000001"
os.environ["TESLA_REGION"] = "na"
os.environ["TESLA_CACHE_ENABLED"] = "false"

from click.testing import CliRunner

from tescmd.cli.main import cli

runner = CliRunner()
result = runner.invoke(cli, ["--format", "json", "--wake", "charge", "limit", "80"])
print("exit_code:", result.exit_code)
print("output:", result.output)
