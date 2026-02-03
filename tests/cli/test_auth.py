"""Tests for auth CLI helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from tescmd.cli.auth import (
    _interactive_setup,
    _prompt_for_domain,
)


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

    def test_shows_concrete_tailscale_url(self) -> None:
        """When tailscale_hostname is passed with full_tier, Step 3 shows the URL."""
        formatter = _make_formatter()
        # Inputs: funnel=n, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            cid, cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        assert cid == "test-id"
        assert cs == "secret"
        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show the concrete Tailscale origin (port 443, no suffix)
        assert any("Also add" in c and "https://mybox.tail99.ts.net" in c for c in calls)
        # Should NOT show the generic placeholder
        assert not any("<machine>.tailnet.ts.net" in c for c in calls)

    def test_generic_placeholder_when_no_tailscale(self) -> None:
        """Without Tailscale, Step 3 shows the generic placeholder hint."""
        formatter = _make_formatter()
        # full_tier=True but no tailscale available → auto-detect fails
        # Inputs: browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
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
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show the generic placeholder
        assert any("<machine>.tailnet.ts.net" in c for c in calls)
        # Should NOT show "Also add"
        assert not any("Also add" in c for c in calls)

    def test_auto_detects_tailscale_when_no_hostname_passed(self) -> None:
        """When tailscale_hostname is empty + full_tier, auto-detection finds Tailscale."""
        formatter = _make_formatter()
        # Inputs: funnel=n, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
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
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Tailscale detected" in c and "auto.tail99.ts.net" in c for c in calls)
        assert any("Also add" in c and "https://auto.tail99.ts.net" in c for c in calls)

    def test_funnel_started_and_stopped(self) -> None:
        """When user accepts Funnel prompt, KeyServer starts and cleanup runs."""
        formatter = _make_formatter()
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 54321)
        # Inputs: funnel=Y, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["Y", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch("tescmd.crypto.keys.has_key_pair", return_value=True),
            patch("tescmd.crypto.keys.load_public_key_pem", return_value="PEM-DATA"),
            patch(
                "tescmd.deploy.tailscale_serve.KeyServer",
                return_value=mock_server,
            ) as mock_ks_cls,
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
                return_value="https://mybox.tail99.ts.net",
            ) as mock_start_funnel,
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.stop_funnel",
                new_callable=AsyncMock,
            ) as mock_stop_funnel,
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        mock_ks_cls.assert_called_once_with("PEM-DATA", port=0)
        mock_server.start.assert_called_once()
        mock_start_funnel.assert_awaited_once_with(54321)
        # Cleanup: KeyServer.stop() + stop_funnel()
        mock_server.stop.assert_called_once()
        mock_stop_funnel.assert_awaited_once()

    def test_funnel_declined_no_cleanup(self) -> None:
        """When user declines Funnel prompt, no Funnel start/stop occurs."""
        formatter = _make_formatter()
        # Inputs: funnel=n, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
            ) as mock_start_funnel,
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        mock_start_funnel.assert_not_called()

    def test_funnel_error_falls_back_to_generic(self) -> None:
        """When start_funnel fails, falls back to generic placeholder."""
        formatter = _make_formatter()
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 54321)
        # Inputs: funnel=Y, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["Y", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch("tescmd.crypto.keys.has_key_pair", return_value=True),
            patch("tescmd.crypto.keys.load_public_key_pem", return_value="PEM-DATA"),
            patch(
                "tescmd.deploy.tailscale_serve.KeyServer",
                return_value=mock_server,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
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
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show the error message
        assert any("Could not start Funnel" in c for c in calls)
        # Should show generic placeholder since ts_hostname was cleared
        assert any("<machine>.tailnet.ts.net" in c for c in calls)
        # KeyServer should have been stopped on failure
        mock_server.stop.assert_called_once()

    def test_funnel_cleanup_failure_warns_user(self) -> None:
        """When Funnel cleanup fails, a warning is shown to the user."""
        formatter = _make_formatter()
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 54321)
        # Inputs: funnel=Y, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["Y", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch("tescmd.crypto.keys.has_key_pair", return_value=True),
            patch("tescmd.crypto.keys.load_public_key_pem", return_value="PEM-DATA"),
            patch(
                "tescmd.deploy.tailscale_serve.KeyServer",
                return_value=mock_server,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
                return_value="https://mybox.tail99.ts.net",
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.stop_funnel",
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
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Failed to stop Tailscale Funnel" in c for c in calls)
        assert any("tailscale funnel --bg off" in c for c in calls)
        # KeyServer.stop() should still have been called
        mock_server.stop.assert_called_once()

    def test_app_name_guid_generated_on_fresh_run(self) -> None:
        """Fresh run generates tescmd-<hex> app name and shows it in Step 2."""
        formatter = _make_formatter()
        # full_tier=True with tailscale: funnel=n, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch("tescmd.cli.auth._write_env_value") as mock_write_val,
            patch.dict("os.environ", {}, clear=False),
            patch("tescmd.cli.auth.uuid") as mock_uuid_mod,
        ):
            # Remove TESLA_APP_NAME if present
            import os

            os.environ.pop("TESLA_APP_NAME", None)
            mock_uuid_mod.uuid4.return_value = MagicMock(hex="aabbccdd11223344")
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Step 2 should show the generated name
        assert any("tescmd-aabbccdd" in c for c in calls)
        # Should persist the app name
        mock_write_val.assert_called_once_with("TESLA_APP_NAME", "tescmd-aabbccdd")

    def test_app_name_reused_from_env_on_rerun(self) -> None:
        """When TESLA_APP_NAME is already set, reuses it and does not re-save."""
        formatter = _make_formatter()
        # full_tier=True with tailscale: funnel=n, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch("tescmd.cli.auth._write_env_value") as mock_write_val,
            patch.dict("os.environ", {"TESLA_APP_NAME": "tescmd-existing1"}, clear=False),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show the existing app name
        assert any("tescmd-existing1" in c for c in calls)
        # Should NOT call _write_env_value since name was already saved
        mock_write_val.assert_not_called()

    def test_eof_on_funnel_prompt_skips_funnel(self) -> None:
        """EOFError on Funnel prompt skips Funnel but continues setup."""
        formatter = _make_formatter()
        # Inputs: funnel=EOFError, browser=n, client_id, secret
        with (
            patch(
                "builtins.input",
                side_effect=[EOFError, "n", "test-id", "secret"],
            ),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
            ) as mock_start_funnel,
        ):
            cid, _cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        # Setup should continue past the Funnel prompt
        assert cid == "test-id"
        mock_start_funnel.assert_not_called()


# ---------------------------------------------------------------------------
# _interactive_setup — full_tier gating
# ---------------------------------------------------------------------------


class TestInteractiveSetupFullTierGating:
    """Verify Tailscale prompt only appears when full_tier=True."""

    def test_no_tailscale_prompt_without_full_tier(self) -> None:
        """When full_tier=False, no Tailscale prompt even if hostname is provided."""
        formatter = _make_formatter()
        # Inputs: browser=n, client_id, secret (no funnel prompt)
        with (
            patch("builtins.input", side_effect=["n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            cid, cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=False,
            )

        assert cid == "test-id"
        assert cs == "secret"
        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should NOT show Tailscale detection or funnel prompt
        assert not any("Tailscale detected" in c for c in calls)
        # Without full_tier, tailscale_hostname is not used for "Also add"
        assert not any("Also add" in c for c in calls)

    def test_no_tailscale_auto_detect_without_full_tier(self) -> None:
        """When full_tier=False, auto-detection is not even attempted."""
        formatter = _make_formatter()
        # Inputs: browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch(
                "tescmd.deploy.tailscale_serve.is_tailscale_serve_ready",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ts_ready,
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                full_tier=False,
            )

        # Auto-detection should not have been called
        mock_ts_ready.assert_not_called()

    def test_default_full_tier_is_false(self) -> None:
        """Default full_tier=False — standalone auth command has no Tailscale prompt."""
        formatter = _make_formatter()
        # Inputs: browser=n, client_id, secret (no funnel prompt)
        with (
            patch("builtins.input", side_effect=["n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            cid, _cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
            )

        assert cid == "test-id"
        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert not any("Tailscale detected" in c for c in calls)


# ---------------------------------------------------------------------------
# _interactive_setup — prompt ordering
# ---------------------------------------------------------------------------


class TestInteractiveSetupPromptOrder:
    """Verify the Tailscale prompt comes before the browser prompt."""

    def test_tailscale_prompt_before_browser(self) -> None:
        """When full_tier=True + Tailscale, funnel prompt precedes browser prompt."""
        formatter = _make_formatter()
        prompts_seen: list[str] = []

        def mock_input(prompt: str = "") -> str:
            prompts_seen.append(prompt)
            if "Funnel" in prompt:
                return "n"
            if "Developer Portal" in prompt:
                return "n"
            if "Client ID" in prompt:
                return "test-id"
            if "Client Secret" in prompt:
                return "secret"
            return ""

        with (
            patch("builtins.input", side_effect=mock_input),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        # Find the indices of key prompts
        funnel_idx = next((i for i, p in enumerate(prompts_seen) if "Funnel" in p), None)
        browser_idx = next(
            (i for i, p in enumerate(prompts_seen) if "Developer Portal" in p), None
        )
        assert funnel_idx is not None, "Funnel prompt not found"
        assert browser_idx is not None, "Browser prompt not found"
        assert funnel_idx < browser_idx, (
            f"Funnel prompt (idx={funnel_idx}) should come before "
            f"browser prompt (idx={browser_idx})"
        )

    def test_steps_uninterrupted_when_full_tier(self) -> None:
        """Steps 1-6 appear contiguously without Tailscale prompts between them."""
        formatter = _make_formatter()
        # Inputs: funnel=n, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Find indices of Steps
        step_indices = []
        for i, c in enumerate(calls):
            if "Step 1" in c:
                step_indices.append(("Step 1", i))
            elif "Step 2" in c:
                step_indices.append(("Step 2", i))
            elif "Step 3" in c:
                step_indices.append(("Step 3", i))
            elif "Step 4" in c:
                step_indices.append(("Step 4", i))
            elif "Step 5" in c:
                step_indices.append(("Step 5", i))
            elif "Step 6" in c:
                step_indices.append(("Step 6", i))

        assert len(step_indices) == 6, f"Expected 6 steps, found {len(step_indices)}"

        # Verify no "Tailscale detected" or "Funnel" messages between Step 1 and Step 6
        first_step_idx = step_indices[0][1]
        last_step_idx = step_indices[-1][1]
        between_steps = calls[first_step_idx : last_step_idx + 1]
        assert not any("Tailscale detected" in c for c in between_steps)
        assert not any("Start Tailscale Funnel" in c for c in between_steps)


# ---------------------------------------------------------------------------
# _interactive_setup — tier-aware scopes
# ---------------------------------------------------------------------------


class TestInteractiveSetupTierAwareScopes:
    """Verify Step 4 scope list changes with full_tier flag."""

    def test_step4_scopes_readonly_tier(self) -> None:
        """When full_tier=False, Step 4 shows only readonly scopes."""
        formatter = _make_formatter()
        # Inputs: browser=n, client_id, secret (no funnel prompt for readonly)
        with (
            patch("builtins.input", side_effect=["n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                full_tier=False,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Readonly scopes present
        assert any("Vehicle Information" in c for c in calls)
        assert any("Vehicle Location" in c for c in calls)
        assert any("Energy Information" in c for c in calls)
        assert any("User Data" in c for c in calls)
        # Command scopes absent
        assert not any("Vehicle Commands" in c for c in calls)
        assert not any("Vehicle Charging Management" in c for c in calls)
        assert not any("Energy Commands" in c for c in calls)

    def test_step4_scopes_full_tier(self) -> None:
        """When full_tier=True, Step 4 says 'Select All' instead of listing scopes."""
        formatter = _make_formatter()
        # Inputs: funnel=n, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        # Should show "Select All" for full tier
        assert any("Select All" in c for c in calls)
        # Individual scope names should NOT appear
        assert not any("Vehicle Information" in c for c in calls)
        assert not any("Vehicle Commands" in c for c in calls)
        assert not any("Vehicle Charging Management" in c for c in calls)
        assert not any("Energy Commands" in c for c in calls)


# ---------------------------------------------------------------------------
# _interactive_setup — key serving
# ---------------------------------------------------------------------------


class TestInteractiveSetupKeyServing:
    """Verify key generation and serving during Funnel start."""

    def test_key_generated_during_funnel_start(self) -> None:
        """When has_key_pair=False, generate_ec_key_pair is called."""
        formatter = _make_formatter()
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 54321)
        # Inputs: funnel=Y, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["Y", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch("tescmd.crypto.keys.has_key_pair", return_value=False),
            patch("tescmd.crypto.keys.generate_ec_key_pair") as mock_gen,
            patch("tescmd.crypto.keys.load_public_key_pem", return_value="PEM-DATA"),
            patch(
                "tescmd.deploy.tailscale_serve.KeyServer",
                return_value=mock_server,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
                return_value="https://mybox.tail99.ts.net",
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.stop_funnel",
                new_callable=AsyncMock,
            ),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        mock_gen.assert_called_once()
        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Generating" in c for c in calls)

    def test_key_not_regenerated_when_exists(self) -> None:
        """When has_key_pair=True, generate_ec_key_pair is NOT called."""
        formatter = _make_formatter()
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 54321)
        # Inputs: funnel=Y, browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["Y", "n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
            patch("tescmd.crypto.keys.has_key_pair", return_value=True),
            patch("tescmd.crypto.keys.generate_ec_key_pair") as mock_gen,
            patch("tescmd.crypto.keys.load_public_key_pem", return_value="PEM-DATA"),
            patch(
                "tescmd.deploy.tailscale_serve.KeyServer",
                return_value=mock_server,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
                return_value="https://mybox.tail99.ts.net",
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.stop_funnel",
                new_callable=AsyncMock,
            ),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        mock_gen.assert_not_called()

    def test_cleanup_runs_on_eof_during_client_id(self) -> None:
        """EOFError at Client ID prompt still triggers KeyServer.stop()."""
        formatter = _make_formatter()
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 54321)
        # Inputs: funnel=Y, browser=n, client_id=EOFError
        with (
            patch("builtins.input", side_effect=["Y", "n", EOFError]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.crypto.keys.has_key_pair", return_value=True),
            patch("tescmd.crypto.keys.load_public_key_pem", return_value="PEM-DATA"),
            patch(
                "tescmd.deploy.tailscale_serve.KeyServer",
                return_value=mock_server,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
                return_value="https://mybox.tail99.ts.net",
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.stop_funnel",
                new_callable=AsyncMock,
            ),
        ):
            cid, cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        assert cid == ""
        assert cs == ""
        mock_server.stop.assert_called_once()

    def test_cleanup_runs_on_empty_client_id(self) -> None:
        """Empty Client ID returns early but still triggers KeyServer.stop()."""
        formatter = _make_formatter()
        mock_server = MagicMock()
        mock_server.server_address = ("127.0.0.1", 54321)
        # Inputs: funnel=Y, browser=n, client_id="" x3 (exhausts retries)
        with (
            patch("builtins.input", side_effect=["Y", "n", "", "", ""]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.crypto.keys.has_key_pair", return_value=True),
            patch("tescmd.crypto.keys.load_public_key_pem", return_value="PEM-DATA"),
            patch(
                "tescmd.deploy.tailscale_serve.KeyServer",
                return_value=mock_server,
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.start_funnel",
                new_callable=AsyncMock,
                return_value="https://mybox.tail99.ts.net",
            ),
            patch(
                "tescmd.telemetry.tailscale.TailscaleManager.stop_funnel",
                new_callable=AsyncMock,
            ),
        ):
            cid, cs = _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
                tailscale_hostname="mybox.tail99.ts.net",
                full_tier=True,
            )

        assert cid == ""
        assert cs == ""
        mock_server.stop.assert_called_once()

    def test_step1_shows_create_new_application(self) -> None:
        """Step 1 header says 'Create New Application', not 'Registration'."""
        formatter = _make_formatter()
        # Inputs: browser=n, client_id, secret
        with (
            patch("builtins.input", side_effect=["n", "test-id", "secret"]),
            patch("tescmd.cli.auth.webbrowser"),
            patch("tescmd.cli.auth._write_env_file"),
        ):
            _interactive_setup(
                formatter,
                8085,
                "http://localhost:8085/callback",
                domain="user.github.io",
            )

        calls = [str(c) for c in formatter.rich.info.call_args_list]
        assert any("Create New Application" in c for c in calls)
        # "Registration" should not appear as a Step 1 header
        assert not any("Step 1" in c and "Registration" in c for c in calls)
