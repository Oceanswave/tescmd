"""Tests for ``tescmd key unenroll`` — virtual key removal instructions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    import pytest

CLIENT_ID = "test-client-id-123"
REVOKE_URL = (
    "https://auth.tesla.com/user/revoke/consent"
    f"?revoke_client_id={CLIENT_ID}&back_url=https://tesla.com"
)


class TestUnenrollRichOutput:
    """Rich output shows removal instructions with all three methods."""

    def test_shows_all_three_methods(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", CLIENT_ID)
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "rich", "key", "unenroll", "--no-open"])
        assert result.exit_code == 0
        output = result.output

        # All three removal methods shown
        assert "touchscreen" in output.lower()
        assert "Tesla app" in output
        assert "accounts.tesla.com" in output

        # Key steps present
        assert "Controls" in output
        assert "Locks" in output
        assert "Third-Party Apps" in output
        assert "key card" in output

    @patch("webbrowser.open")
    def test_opens_revocation_url_by_default(
        self,
        mock_open: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", CLIENT_ID)
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "rich", "key", "unenroll"])
        assert result.exit_code == 0
        mock_open.assert_called_once_with(REVOKE_URL)  # type: ignore[union-attr]

    @patch("webbrowser.open")
    def test_no_open_skips_browser(
        self,
        mock_open: object,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", CLIENT_ID)
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "rich", "key", "unenroll", "--no-open"])
        assert result.exit_code == 0
        mock_open.assert_not_called()  # type: ignore[union-attr]

    def test_no_client_id_shows_guidance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", "")
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "rich", "key", "unenroll", "--no-open"])
        assert result.exit_code == 0
        assert "TESLA_CLIENT_ID" in result.output

    def test_shows_local_cleanup_commands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", CLIENT_ID)
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "rich", "key", "unenroll", "--no-open"])
        assert result.exit_code == 0
        assert "auth logout" in result.output
        assert "cache clear" in result.output


class TestUnenrollJsonOutput:
    """JSON output includes structured removal instructions."""

    def test_json_with_client_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", CLIENT_ID)
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "key", "unenroll", "--no-open"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        data = output["data"]
        assert data["status"] == "instructions"
        assert data["revoke_url"] == REVOKE_URL
        assert len(data["methods"]) == 3
        assert data["methods"][0]["name"] == "vehicle_touchscreen"
        assert data["methods"][0]["speed"] == "immediate"

    def test_json_without_client_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", "")
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "key", "unenroll", "--no-open"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        data = output["data"]
        assert data["revoke_url"] is None
        assert "TESLA_CLIENT_ID" in data["message"]

    def test_json_methods_have_correct_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CLIENT_ID", CLIENT_ID)
        monkeypatch.setenv("TESLA_CONFIG_DIR", "/tmp/fake")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "key", "unenroll", "--no-open"])
        output = json.loads(result.output)
        methods = output["data"]["methods"]
        for method in methods:
            assert "name" in method
            assert "steps" in method
            assert "speed" in method
