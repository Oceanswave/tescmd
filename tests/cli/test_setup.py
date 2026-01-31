"""Tests for the setup wizard CLI command."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tescmd.cli.main import AppContext
from tescmd.cli.setup import (
    TIER_FULL,
    TIER_READONLY,
    _cmd_setup,
    _precheck_public_key,
    _print_next_steps,
    _prompt_tier,
    _registration_step,
)


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


def _make_formatter(fmt: str = "rich") -> MagicMock:
    """Create a mock OutputFormatter with the given format."""
    formatter = MagicMock()
    formatter.format = fmt
    formatter.rich = MagicMock()
    formatter.rich.info = MagicMock()
    formatter.rich.error = MagicMock()
    formatter.output = MagicMock()
    formatter.output_error = MagicMock()
    return formatter


# ---------------------------------------------------------------------------
# Phase 0: Tier selection
# ---------------------------------------------------------------------------


class TestPromptTier:
    def test_existing_readonly_keeps_when_declined(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_SETUP_TIER", "readonly")

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with patch("builtins.input", return_value=""):
            tier = _prompt_tier(formatter, settings)
        assert tier == TIER_READONLY

    def test_existing_readonly_upgrades_to_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_SETUP_TIER", "readonly")

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with (
            patch("builtins.input", return_value="y"),
            patch("tescmd.cli.auth._write_env_value"),
        ):
            tier = _prompt_tier(formatter, settings)
        assert tier == TIER_FULL

    def test_existing_full_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_SETUP_TIER", "full")

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        tier = _prompt_tier(formatter, settings)
        assert tier == TIER_FULL

    def test_choose_readonly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with patch("builtins.input", return_value="1"), patch("tescmd.cli.auth._write_env_value"):
            tier = _prompt_tier(formatter, settings)

        assert tier == TIER_READONLY

    def test_choose_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with patch("builtins.input", return_value="2"), patch("tescmd.cli.auth._write_env_value"):
            tier = _prompt_tier(formatter, settings)

        assert tier == TIER_FULL

    def test_default_is_readonly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with patch("builtins.input", return_value=""), patch("tescmd.cli.auth._write_env_value"):
            tier = _prompt_tier(formatter, settings)

        assert tier == TIER_READONLY

    def test_eof_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with patch("builtins.input", side_effect=EOFError):
            tier = _prompt_tier(formatter, settings)

        assert tier == ""


# ---------------------------------------------------------------------------
# Phase 2: Domain setup — lowercase validation
# ---------------------------------------------------------------------------


class TestAutomatedDomainSetup:
    def test_lowercases_github_username_in_domain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.cli.setup import _automated_domain_setup
        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with (
            patch(
                "tescmd.deploy.github_pages.get_gh_username",
                return_value="Testuser",
            ),
            patch(
                "tescmd.deploy.github_pages.create_pages_repo",
                return_value="Testuser/Testuser.github.io",
            ),
            patch(
                "tescmd.deploy.github_pages.get_pages_domain",
                return_value="testuser.github.io",
            ),
            patch("builtins.input", return_value="Y"),
            patch("tescmd.cli.auth._write_env_value") as mock_write,
        ):
            domain = _automated_domain_setup(formatter, settings)

        assert domain == "testuser.github.io"
        # Verify the lowercased domain was persisted
        mock_write.assert_any_call("TESLA_DOMAIN", "testuser.github.io")


# ---------------------------------------------------------------------------
# Phase 6: Next steps
# ---------------------------------------------------------------------------


class TestPrintNextSteps:
    def test_readonly_next_steps(self) -> None:
        formatter = _make_formatter()
        _print_next_steps(formatter, TIER_READONLY)

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("vehicle list" in c for c in calls)
        assert any("upgrade" in c.lower() for c in calls)

    def test_full_next_steps(self) -> None:
        formatter = _make_formatter()
        _print_next_steps(formatter, TIER_FULL)

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("vehicle list" in c for c in calls)
        assert any("enroll" in c.lower() for c in calls)


# ---------------------------------------------------------------------------
# Full wizard flow (mocked)
# ---------------------------------------------------------------------------


class TestCmdSetup:
    @pytest.mark.asyncio
    async def test_cancels_on_empty_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        app_ctx = _make_app_ctx()

        with patch("tescmd.cli.setup._prompt_tier", return_value=""):
            await _cmd_setup(app_ctx)

        # Should have returned early — no portal setup called
        # (No assertion on specific calls; the absence of errors is the test)

    @pytest.mark.asyncio
    async def test_cancels_on_empty_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        app_ctx = _make_app_ctx()

        with (
            patch("tescmd.cli.setup._prompt_tier", return_value=TIER_READONLY),
            patch(
                "tescmd.cli.setup._developer_portal_setup",
                return_value=("", ""),
            ),
        ):
            await _cmd_setup(app_ctx)

    @pytest.mark.asyncio
    async def test_readonly_flow_skips_key_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CLIENT_ID", "test-id")
        monkeypatch.setenv("TESLA_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("TESLA_DOMAIN", "user.github.io")

        app_ctx = _make_app_ctx()

        with (
            patch("tescmd.cli.setup._prompt_tier", return_value=TIER_READONLY),
            patch(
                "tescmd.cli.setup._developer_portal_setup",
                return_value=("test-id", "test-secret"),
            ),
            patch("tescmd.cli.setup._domain_setup", return_value="user.github.io"),
            patch("tescmd.cli.setup._key_setup") as mock_key,
            patch(
                "tescmd.cli.setup._registration_step",
                new_callable=AsyncMock,
            ),
            patch(
                "tescmd.cli.setup._oauth_login_step",
                new_callable=AsyncMock,
            ),
        ):
            await _cmd_setup(app_ctx)
            mock_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_full_flow_includes_key_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TESLA_CLIENT_ID", "test-id")
        monkeypatch.setenv("TESLA_CLIENT_SECRET", "test-secret")
        monkeypatch.setenv("TESLA_DOMAIN", "user.github.io")

        app_ctx = _make_app_ctx()

        with (
            patch("tescmd.cli.setup._prompt_tier", return_value=TIER_FULL),
            patch(
                "tescmd.cli.setup._developer_portal_setup",
                return_value=("test-id", "test-secret"),
            ),
            patch("tescmd.cli.setup._domain_setup", return_value="user.github.io"),
            patch("tescmd.cli.setup._key_setup") as mock_key,
            patch(
                "tescmd.cli.setup._enrollment_step",
                new_callable=AsyncMock,
            ),
            patch(
                "tescmd.cli.setup._registration_step",
                new_callable=AsyncMock,
            ),
            patch(
                "tescmd.cli.setup._oauth_login_step",
                new_callable=AsyncMock,
            ),
        ):
            await _cmd_setup(app_ctx)
            mock_key.assert_called_once()


# ---------------------------------------------------------------------------
# Phase 4: Registration — precheck and error remediation
# ---------------------------------------------------------------------------


class TestPrecheckPublicKey:
    """Tests for _precheck_public_key (runs before registration)."""

    def test_key_already_accessible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with patch("tescmd.deploy.github_pages.validate_key_url", return_value=True):
            result = _precheck_public_key(formatter, settings, "user.github.io")

        assert result is True
        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("accessible" in c.lower() for c in calls)

    def test_key_missing_user_accepts_auto_deploy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with (
            patch("tescmd.deploy.github_pages.validate_key_url", return_value=False),
            patch("builtins.input", return_value="Y"),
            patch("tescmd.cli.setup._auto_deploy_key", return_value=True) as mock_deploy,
        ):
            result = _precheck_public_key(formatter, settings, "user.github.io")

        assert result is True
        mock_deploy.assert_called_once_with(formatter, settings, "user.github.io")

    def test_key_missing_user_declines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with (
            patch("tescmd.deploy.github_pages.validate_key_url", return_value=False),
            patch("builtins.input", return_value="n"),
        ):
            result = _precheck_public_key(formatter, settings, "user.github.io")

        assert result is False
        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Shows 424 remediation steps
        assert any("How to fix" in c for c in calls)
        assert any("tescmd key generate" in c for c in calls)

    def test_key_missing_eof_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        formatter = _make_formatter()

        with (
            patch("tescmd.deploy.github_pages.validate_key_url", return_value=False),
            patch("builtins.input", side_effect=EOFError),
        ):
            result = _precheck_public_key(formatter, settings, "user.github.io")

        assert result is False


class TestRegistrationStep:
    """Tests for _registration_step (precheck + actual registration)."""

    @pytest.mark.asyncio
    async def test_412_origin_mismatch_shows_remediation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.api.errors import AuthError
        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        app_ctx = _make_app_ctx()
        formatter = app_ctx.formatter

        error = AuthError(
            "Partner registration failed (HTTP 412): "
            '{"error":"Root domain user.github.io must match registered allowed origin"}',
            status_code=412,
        )

        with (
            patch("tescmd.cli.setup._precheck_public_key", return_value=True),
            patch("tescmd.auth.oauth.register_partner_account", side_effect=error),
        ):
            await _registration_step(
                formatter, app_ctx, settings, "test-id", "test-secret", "user.github.io"
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("How to fix" in c for c in calls)
        assert any("Allowed Origin URL" in c for c in calls)
        assert any("https://user.github.io" in c for c in calls)
        assert any("developer.tesla.com" in c for c in calls)

    @pytest.mark.asyncio
    async def test_generic_error_shows_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        app_ctx = _make_app_ctx()
        formatter = app_ctx.formatter

        with (
            patch("tescmd.cli.setup._precheck_public_key", return_value=True),
            patch(
                "tescmd.auth.oauth.register_partner_account",
                side_effect=Exception("Connection refused"),
            ),
        ):
            await _registration_step(
                formatter, app_ctx, settings, "test-id", "test-secret", "user.github.io"
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("retry" in c.lower() for c in calls)
        assert not any("How to fix" in c for c in calls)

    @pytest.mark.asyncio
    async def test_skips_when_no_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        app_ctx = _make_app_ctx()
        formatter = app_ctx.formatter

        await _registration_step(formatter, app_ctx, settings, "test-id", "", "user.github.io")

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Skipping" in c for c in calls)

    @pytest.mark.asyncio
    async def test_skips_when_precheck_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        app_ctx = _make_app_ctx()
        formatter = app_ctx.formatter

        with patch("tescmd.cli.setup._precheck_public_key", return_value=False):
            await _registration_step(
                formatter, app_ctx, settings, "test-id", "test-secret", "user.github.io"
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Skipping registration" in c for c in calls)

    @pytest.mark.asyncio
    async def test_424_fallback_shows_remediation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Edge case: precheck passed but Tesla still returned 424."""
        for key in list(os.environ):
            if key.startswith("TESLA_"):
                monkeypatch.delenv(key, raising=False)

        from tescmd.api.errors import AuthError
        from tescmd.models.config import AppSettings

        settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
        app_ctx = _make_app_ctx()
        formatter = app_ctx.formatter

        error = AuthError(
            "Partner registration failed (HTTP 424): "
            '{"error":"Public key download failed for '
            "https://user.github.io/.well-known/appspecific/"
            'com.tesla.3p.public-key.pem"}',
            status_code=424,
        )

        with (
            patch("tescmd.cli.setup._precheck_public_key", return_value=True),
            patch("tescmd.auth.oauth.register_partner_account", side_effect=error),
        ):
            await _registration_step(
                formatter, app_ctx, settings, "test-id", "test-secret", "user.github.io"
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("How to fix" in c for c in calls)
        assert any("public key" in c.lower() for c in calls)
        assert any("tescmd key generate" in c for c in calls)
        assert any(".well-known" in c for c in calls)
