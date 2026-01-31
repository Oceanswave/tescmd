"""Tests for ``tescmd key enroll`` — Tesla app portal enrollment flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOMAIN = "testuser.github.io"
FINGERPRINT = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
ENROLL_URL = f"https://tesla.com/_ak/{DOMAIN}"
KEY_URL = f"https://{DOMAIN}/.well-known/appspecific/com.tesla.3p.public-key.pem"


@pytest.fixture()
def _fake_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create fake key files and patch AppSettings to use them."""
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    (key_dir / "private_key.pem").write_text("fake-private")
    (key_dir / "public_key.pem").write_text("fake-public")

    monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("TESLA_DOMAIN", DOMAIN)
    monkeypatch.setenv("TESLA_SETUP_TIER", "full")
    return key_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnrollNoKeys:
    """When no key pair exists, enroll should error."""

    def test_enroll_no_keys_rich(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_DOMAIN", DOMAIN)

        runner = CliRunner()
        result = runner.invoke(cli, ["key", "enroll"])
        assert result.exit_code != 0
        assert "key generate" in result.output.lower() or "no key pair" in result.output.lower()

    def test_enroll_no_keys_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_DOMAIN", DOMAIN)

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "key", "enroll"])
        assert result.exit_code != 0
        assert "no_keys" in result.output


class TestEnrollNoDomain:
    """When no domain is configured, enroll should error."""

    @patch("tescmd.cli.key.get_key_fingerprint", return_value=FINGERPRINT)
    def test_enroll_no_domain_rich(
        self,
        _mock_fp: object,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "private_key.pem").write_text("fake-private")
        (key_dir / "public_key.pem").write_text("fake-public")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_DOMAIN", "")

        runner = CliRunner()
        result = runner.invoke(cli, ["key", "enroll"])
        assert result.exit_code != 0
        assert "domain" in result.output.lower()

    @patch("tescmd.cli.key.get_key_fingerprint", return_value=FINGERPRINT)
    def test_enroll_no_domain_json(
        self,
        _mock_fp: object,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "private_key.pem").write_text("fake-private")
        (key_dir / "public_key.pem").write_text("fake-public")
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", "test-token")
        monkeypatch.setenv("TESLA_DOMAIN", "")

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "key", "enroll"])
        assert result.exit_code != 0
        assert "no_domain" in result.output


class TestEnrollKeyNotAccessible:
    """When the public key isn't accessible at the domain URL."""

    @patch("tescmd.cli.key.validate_key_url", return_value=False)
    @patch("tescmd.cli.key.get_key_url", return_value=KEY_URL)
    @patch("tescmd.cli.key.get_key_fingerprint", return_value=FINGERPRINT)
    def test_enroll_key_not_accessible_rich(
        self,
        _mock_fp: object,
        _mock_url: object,
        _mock_validate: object,
        _fake_keys: Path,
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["key", "enroll", "--no-open"])
        assert result.exit_code != 0
        assert "not accessible" in result.output.lower() or "deploy" in result.output.lower()

    @patch("tescmd.cli.key.validate_key_url", return_value=False)
    @patch("tescmd.cli.key.get_key_url", return_value=KEY_URL)
    @patch("tescmd.cli.key.get_key_fingerprint", return_value=FINGERPRINT)
    def test_enroll_key_not_accessible_json(
        self,
        _mock_fp: object,
        _mock_url: object,
        _mock_validate: object,
        _fake_keys: Path,
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "key", "enroll", "--no-open"])
        assert result.exit_code != 0
        assert "key_not_accessible" in result.output


class TestEnrollSuccess:
    """Happy path: keys exist, domain set, key accessible."""

    @patch("tescmd.cli.key.validate_key_url", return_value=True)
    @patch("tescmd.cli.key.get_key_url", return_value=KEY_URL)
    @patch("tescmd.cli.key.get_key_fingerprint", return_value=FINGERPRINT)
    def test_enroll_rich_shows_url(
        self,
        _mock_fp: object,
        _mock_url: object,
        _mock_validate: object,
        _fake_keys: Path,
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["key", "enroll", "--no-open"])
        assert result.exit_code == 0
        assert ENROLL_URL in result.output
        assert "tesla app" in result.output.lower() or "approve" in result.output.lower()

    @patch("tescmd.cli.key.validate_key_url", return_value=True)
    @patch("tescmd.cli.key.get_key_url", return_value=KEY_URL)
    @patch("tescmd.cli.key.get_key_fingerprint", return_value=FINGERPRINT)
    def test_enroll_json_envelope(
        self,
        _mock_fp: object,
        _mock_url: object,
        _mock_validate: object,
        _fake_keys: Path,
    ) -> None:
        import json

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "key", "enroll", "--no-open"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["status"] == "ready"
        assert data["data"]["domain"] == DOMAIN
        assert data["data"]["enroll_url"] == ENROLL_URL
        assert data["data"]["fingerprint"] == FINGERPRINT

    @patch("tescmd.cli.key.validate_key_url", return_value=True)
    @patch("tescmd.cli.key.get_key_url", return_value=KEY_URL)
    @patch("tescmd.cli.key.get_key_fingerprint", return_value=FINGERPRINT)
    def test_enroll_no_open_skips_browser(
        self,
        _mock_fp: object,
        _mock_url: object,
        _mock_validate: object,
        _fake_keys: Path,
    ) -> None:
        with patch("webbrowser.open") as mock_browser:
            runner = CliRunner()
            result = runner.invoke(cli, ["key", "enroll", "--no-open"])
            assert result.exit_code == 0
            mock_browser.assert_not_called()
