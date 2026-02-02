"""Tests for auth CLI helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tescmd.cli.auth import _interactive_setup, _prompt_for_domain


def _make_formatter() -> MagicMock:
    formatter = MagicMock()
    formatter.format = "rich"
    formatter.rich = MagicMock()
    formatter.rich.info = MagicMock()
    return formatter


class TestPromptForDomain:
    def test_lowercases_user_input(self) -> None:
        formatter = _make_formatter()
        with (
            patch("builtins.input", return_value="Testuser.GitHub.IO"),
            patch("tescmd.cli.auth._write_env_value"),
        ):
            domain = _prompt_for_domain(formatter)
        assert domain == "testuser.github.io"

    def test_strips_https_and_lowercases(self) -> None:
        formatter = _make_formatter()
        with (
            patch("builtins.input", return_value="https://MyDomain.Example.COM/"),
            patch("tescmd.cli.auth._write_env_value"),
        ):
            domain = _prompt_for_domain(formatter)
        assert domain == "mydomain.example.com"

    def test_strips_http_and_lowercases(self) -> None:
        formatter = _make_formatter()
        with (
            patch("builtins.input", return_value="http://UPPERCASE.github.io/"),
            patch("tescmd.cli.auth._write_env_value"),
        ):
            domain = _prompt_for_domain(formatter)
        assert domain == "uppercase.github.io"

    def test_already_lowercase_unchanged(self) -> None:
        formatter = _make_formatter()
        with (
            patch("builtins.input", return_value="valid.github.io"),
            patch("tescmd.cli.auth._write_env_value"),
        ):
            domain = _prompt_for_domain(formatter)
        assert domain == "valid.github.io"

    def test_empty_input_returns_empty(self) -> None:
        formatter = _make_formatter()
        with patch("builtins.input", return_value=""):
            domain = _prompt_for_domain(formatter)
        assert domain == ""

    def test_eof_returns_empty(self) -> None:
        formatter = _make_formatter()
        with patch("builtins.input", side_effect=EOFError):
            domain = _prompt_for_domain(formatter)
        assert domain == ""

    def test_persists_lowercased_value(self) -> None:
        formatter = _make_formatter()
        with (
            patch("builtins.input", return_value="MixedCase.GitHub.IO"),
            patch("tescmd.cli.auth._write_env_value") as mock_write,
        ):
            _prompt_for_domain(formatter)
        mock_write.assert_called_once_with("TESLA_DOMAIN", "mixedcase.github.io")


# ---------------------------------------------------------------------------
# _interactive_setup — Tailscale origin URL
# ---------------------------------------------------------------------------


class TestInteractiveSetupTailscaleOrigin:
    """Tests for Tailscale detection + Funnel lifecycle in _interactive_setup."""

    def test_shows_concrete_tailscale_url_when_hostname_provided(self) -> None:
        """When tailscale_hostname is passed, Step 3 shows 'Also add' with concrete URL."""
        formatter = _make_formatter()
        # Inputs: open browser=n, funnel prompt=n, client_id, secret, save=n
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret", "n"]),
            patch("tescmd.cli.auth.webbrowser"),
        ):
            cid, cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
            )

        assert cid == "test-id"
        assert cs == "secret"
        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show the concrete Tailscale origin
        assert any("Also add" in c and "https://mybox.tail99.ts.net" in c for c in calls)
        # Should NOT show the generic placeholder
        assert not any("<machine>.tailnet.ts.net" in c for c in calls)

    def test_generic_placeholder_when_no_tailscale(self) -> None:
        """Without Tailscale, Step 3 shows the generic placeholder hint."""
        formatter = _make_formatter()
        # Inputs: open browser=n, client_id, secret, save=n
        with (
            patch("builtins.input", side_effect=["n", "test-id", "secret", "n"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch(
                "tescmd.deploy.tailscale_serve.is_tailscale_serve_ready",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show the generic placeholder
        assert any("<machine>.tailnet.ts.net" in c for c in calls)
        # Should NOT show "Also add"
        assert not any("Also add" in c for c in calls)

    def test_auto_detects_tailscale_when_no_hostname_passed(self) -> None:
        """When tailscale_hostname is empty, auto-detection finds Tailscale."""
        formatter = _make_formatter()
        # Inputs: open browser=n, funnel prompt=n, client_id, secret, save=n
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret", "n"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch(
                "tescmd.deploy.tailscale_serve.is_tailscale_serve_ready",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.get_hostname",
                new_callable=AsyncMock,
                return_value="auto.tail99.ts.net",
            ),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Tailscale detected" in c and "auto.tail99.ts.net" in c for c in calls)
        assert any("Also add" in c and "https://auto.tail99.ts.net" in c for c in calls)

    def test_funnel_started_and_stopped(self) -> None:
        """When user accepts Funnel prompt, enable_funnel is called and cleanup runs."""
        formatter = _make_formatter()
        # Inputs: open browser=n, funnel=Y, client_id, secret, save=n
        with (
            patch("builtins.input", side_effect=["n", "Y", "test-id", "secret", "n"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.enable_funnel",
                new_callable=AsyncMock,
            ) as mock_enable,
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager._run",
                new_callable=AsyncMock,
                return_value=(0, "", ""),
            ) as mock_run,
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
            )

        mock_enable.assert_called_once()
        # Cleanup: _run called with funnel off
        mock_run.assert_called_once_with("tailscale", "funnel", "--bg", "off")

    def test_funnel_declined_no_cleanup(self) -> None:
        """When user declines Funnel prompt, no Funnel start/stop occurs."""
        formatter = _make_formatter()
        # Inputs: open browser=n, funnel=n, client_id, secret, save=n
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret", "n"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.enable_funnel",
                new_callable=AsyncMock,
            ) as mock_enable,
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager._run",
                new_callable=AsyncMock,
            ) as mock_run,
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
            )

        mock_enable.assert_not_called()
        mock_run.assert_not_called()

    def test_funnel_error_falls_back_to_generic(self) -> None:
        """When Funnel start fails, falls back to generic placeholder."""
        formatter = _make_formatter()
        # Inputs: open browser=n, funnel=Y, client_id, secret, save=n
        with (
            patch("builtins.input", side_effect=["n", "Y", "test-id", "secret", "n"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.enable_funnel",
                new_callable=AsyncMock,
                side_effect=Exception("Funnel not available"),
            ),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show the error message
        assert any("Could not start Funnel" in c for c in calls)
        # Should show generic placeholder since ts_hostname was cleared
        assert any("<machine>.tailnet.ts.net" in c for c in calls)

    def test_funnel_cleanup_failure_warns_user(self) -> None:
        """When Funnel cleanup fails, a warning is shown to the user."""
        formatter = _make_formatter()
        # Inputs: open browser=n, funnel=Y, client_id, secret, save=n
        with (
            patch("builtins.input", side_effect=["n", "Y", "test-id", "secret", "n"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.enable_funnel",
                new_callable=AsyncMock,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager._run",
                new_callable=AsyncMock,
                side_effect=Exception("network timeout"),
            ),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Failed to stop Tailscale Funnel" in c for c in calls)
        assert any("tailscale funnel --bg off" in c for c in calls)

    def test_eof_on_funnel_prompt_skips_funnel(self) -> None:
        """EOFError on Funnel prompt skips Funnel but continues setup."""
        formatter = _make_formatter()
        # Inputs: open browser=n, funnel=EOFError, client_id, secret, save=n
        with (
            patch(
                "builtins.input",
                side_effect=["n", EOFError, "test-id", "secret", "n"],
            ),
            patch("tescmd.cli.auth.webbrowser"),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.enable_funnel",
                new_callable=AsyncMock,
            ) as mock_enable,
        ):
            cid, _cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
            )

        # Setup should continue past the Funnel prompt
        assert cid == "test-id"
        mock_enable.assert_not_called()
