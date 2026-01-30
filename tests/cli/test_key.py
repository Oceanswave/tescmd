"""Tests for the key CLI command group."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from tescmd.cli.key import _cmd_deploy, _cmd_generate, _cmd_show, _cmd_validate
from tescmd.cli.main import AppContext

if TYPE_CHECKING:
    from pathlib import Path


def _make_app_ctx(fmt: str = "rich", **kwargs: object) -> AppContext:
    """Create an AppContext with common defaults plus overrides."""
    defaults: dict[str, object] = {
        "vin": None,
        "profile": "default",
        "output_format": None,
        "quiet": False,
        "region": None,
        "verbose": False,
    }
    defaults.update(kwargs)
    ctx = AppContext(**defaults)  # type: ignore[arg-type]
    # Inject a mock formatter
    formatter = MagicMock()
    formatter.format = fmt
    formatter.rich = MagicMock()
    formatter.rich.info = MagicMock()
    formatter.rich.error = MagicMock()
    formatter.output = MagicMock()
    formatter.output_error = MagicMock()
    ctx._formatter = formatter
    return ctx


class TestCmdGenerate:
    @pytest.mark.asyncio
    async def test_generates_keys(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        app_ctx = _make_app_ctx("rich")

        await _cmd_generate(app_ctx, force=False)

        key_dir = tmp_path / "keys"
        assert (key_dir / "private_key.pem").exists()
        assert (key_dir / "public_key.pem").exists()
        app_ctx.formatter.rich.info.assert_called()

    @pytest.mark.asyncio
    async def test_generate_json_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        app_ctx = _make_app_ctx("json")

        await _cmd_generate(app_ctx, force=False)

        app_ctx.formatter.output.assert_called_once()
        data = app_ctx.formatter.output.call_args[0][0]
        assert data["status"] == "generated"
        assert "fingerprint" in data

    @pytest.mark.asyncio
    async def test_existing_keys_no_force(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        # Generate first
        app_ctx = _make_app_ctx("rich")
        await _cmd_generate(app_ctx, force=False)

        # Try again without force
        app_ctx2 = _make_app_ctx("rich")
        await _cmd_generate(app_ctx2, force=False)

        # Should mention existing keys
        calls = [str(c) for c in app_ctx2.formatter.rich.info.call_args_list]
        assert any("already exists" in c for c in calls)

    @pytest.mark.asyncio
    async def test_force_overwrite(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        app_ctx = _make_app_ctx("rich")
        await _cmd_generate(app_ctx, force=False)

        # Force overwrite
        app_ctx2 = _make_app_ctx("rich")
        await _cmd_generate(app_ctx2, force=True)

        calls = [str(c) for c in app_ctx2.formatter.rich.info.call_args_list]
        assert any("generated" in c.lower() for c in calls)


class TestCmdShow:
    @pytest.mark.asyncio
    async def test_no_keys(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        app_ctx = _make_app_ctx("rich")

        await _cmd_show(app_ctx)
        calls = [str(c) for c in app_ctx.formatter.rich.info.call_args_list]
        assert any("not found" in c.lower() or "generate" in c.lower() for c in calls)

    @pytest.mark.asyncio
    async def test_shows_key_info(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        # Generate keys first
        from tescmd.crypto.keys import generate_ec_key_pair

        generate_ec_key_pair(tmp_path / "keys")

        app_ctx = _make_app_ctx("rich")
        await _cmd_show(app_ctx)

        calls = [str(c) for c in app_ctx.formatter.rich.info.call_args_list]
        assert any("fingerprint" in c.lower() for c in calls)

    @pytest.mark.asyncio
    async def test_json_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        from tescmd.crypto.keys import generate_ec_key_pair

        generate_ec_key_pair(tmp_path / "keys")

        app_ctx = _make_app_ctx("json")
        await _cmd_show(app_ctx)

        app_ctx.formatter.output.assert_called_once()
        data = app_ctx.formatter.output.call_args[0][0]
        assert data["status"] == "found"
        assert "fingerprint" in data


class TestCmdValidate:
    @pytest.mark.asyncio
    async def test_no_domain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        mock_settings = MagicMock()
        mock_settings.domain = None
        with patch("tescmd.cli.key.AppSettings", return_value=mock_settings):
            app_ctx = _make_app_ctx("rich")
            await _cmd_validate(app_ctx)

        app_ctx.formatter.rich.error.assert_called()

    @pytest.mark.asyncio
    async def test_valid_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_DOMAIN", "user.github.io")

        with patch("tescmd.cli.key.validate_key_url", return_value=True):
            app_ctx = _make_app_ctx("rich")
            await _cmd_validate(app_ctx)

        calls = [str(c) for c in app_ctx.formatter.rich.info.call_args_list]
        assert any("accessible" in c.lower() for c in calls)

    @pytest.mark.asyncio
    async def test_invalid_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_DOMAIN", "user.github.io")

        with patch("tescmd.cli.key.validate_key_url", return_value=False):
            app_ctx = _make_app_ctx("rich")
            await _cmd_validate(app_ctx)

        calls = [str(c) for c in app_ctx.formatter.rich.info.call_args_list]
        assert any("not accessible" in c.lower() for c in calls)

    @pytest.mark.asyncio
    async def test_json_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_DOMAIN", "user.github.io")

        with patch("tescmd.cli.key.validate_key_url", return_value=True):
            app_ctx = _make_app_ctx("json")
            await _cmd_validate(app_ctx)

        app_ctx.formatter.output.assert_called_once()
        data = app_ctx.formatter.output.call_args[0][0]
        assert data["accessible"] is True


class TestCmdDeploy:
    @pytest.mark.asyncio
    async def test_no_keys_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        app_ctx = _make_app_ctx("rich")
        await _cmd_deploy(app_ctx, repo=None)

        app_ctx.formatter.rich.error.assert_called()

    @pytest.mark.asyncio
    async def test_gh_not_available(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CONFIG_DIR", str(tmp_path))

        from tescmd.crypto.keys import generate_ec_key_pair

        generate_ec_key_pair(tmp_path / "keys")

        with patch("tescmd.deploy.github_pages.shutil.which", return_value=None):
            app_ctx = _make_app_ctx("rich")
            await _cmd_deploy(app_ctx, repo=None)

        app_ctx.formatter.rich.error.assert_called()
