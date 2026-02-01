"""End-to-end smoke tests for every tescmd CLI command.

Runs against the LIVE Tesla Fleet API — requires a valid TESLA_ACCESS_TOKEN
in the environment.  Excluded from the default pytest run by the ``e2e`` marker;
invoke explicitly with::

    pytest -m e2e -x -v tests/cli/test_e2e_smoke.py

Design:
    - Uses Click's CliRunner (in-process, no subprocess overhead).
    - ``--format json`` + ``--wake`` on all live commands so output is
      machine-parseable and the vehicle wakes automatically.
    - Validates the JSON envelope structure on every response.
    - ``--help`` commands just verify exit-code 0 and non-trivial output.
    - Benign write commands record pre-state and restore in a ``finally`` block.
    - Known API errors (vehicle_asleep, auth_failed, tier_readonly, …) are
      treated as *valid* responses (the CLI produced a well-formed envelope).
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from click.testing import CliRunner, Result

from tescmd.api.errors import (
    AuthError,
    CommandFailedError,
    ConfigError,
    KeyNotEnrolledError,
    MissingScopesError,
    NetworkError,
    RateLimitError,
    RegistrationRequiredError,
    SessionError,
    TeslaAPIError,
    TierError,
    TunnelError,
    VehicleAsleepError,
    VehicleNotFoundError,
)
from tescmd.cli.main import cli

# Known exception types that represent a valid (non-crash) CLI response.
# When CliRunner catches these, it means the command ran but the Fleet API
# returned an expected error — the test should pass.
KNOWN_API_ERRORS = (
    AuthError,
    MissingScopesError,
    VehicleAsleepError,
    VehicleNotFoundError,
    CommandFailedError,
    RateLimitError,
    RegistrationRequiredError,
    NetworkError,
    ConfigError,
    TierError,
    SessionError,
    KeyNotEnrolledError,
    TunnelError,
    TeslaAPIError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIN = os.environ.get("E2E_VIN", "")
SITE_ID = os.environ.get("E2E_SITE_ID", "")

pytestmark = pytest.mark.e2e

_requires_vin = pytest.mark.skipif(not VIN, reason="E2E_VIN not set")
_requires_site = pytest.mark.skipif(not SITE_ID, reason="E2E_SITE_ID not set")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def e2e_runner() -> CliRunner:
    """CliRunner with stderr separated so we can inspect error envelopes."""
    return CliRunner(mix_stderr=False)


@pytest.fixture(scope="module")
def e2e_env() -> dict[str, str]:
    """Environment dict with real credentials and VIN."""
    env = {
        "TESLA_VIN": VIN,
        "TESLA_OUTPUT_FORMAT": "json",
    }
    # Propagate real credentials from the outer environment
    for key in (
        "TESLA_ACCESS_TOKEN",
        "TESLA_REFRESH_TOKEN",
        "TESLA_CLIENT_ID",
        "TESLA_CLIENT_SECRET",
        "TESLA_REGION",
        "TESLA_DOMAIN",
        "TESLA_CONFIG_DIR",
        "TESLA_TOKEN_FILE",
        "TESLA_SETUP_TIER",
        "TESLA_COMMAND_PROTOCOL",
        "TESLA_HOSTING_METHOD",
        "TESLA_GITHUB_REPO",
    ):
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    return env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invoke_e2e(
    runner: CliRunner,
    env: dict[str, str],
    args: list[str],
    *,
    extra_flags: list[str] | None = None,
    input_text: str | None = None,
) -> Result:
    """Invoke the CLI and return the full :class:`click.testing.Result`."""
    full_args: list[str] = ["--format", "json"]
    if extra_flags:
        full_args.extend(extra_flags)
    full_args.extend(args)
    return runner.invoke(
        cli,
        full_args,
        env=env,
        catch_exceptions=True,
        input=input_text,
    )


def assert_valid_response(
    result: Result,
    *,
    allow_error: bool = True,
) -> dict[str, Any] | None:
    """Validate the JSON envelope from a live command.

    CliRunner catches all exceptions when ``catch_exceptions=True``.
    Because we invoke the Click group directly (not ``main()``), the
    ``main()`` error handler doesn't fire — so expected API errors
    (auth, scope, tier, asleep, …) show up in ``result.exception``
    with empty output.  We accept those as valid "the command ran and
    the API responded".

    Returns the parsed envelope dict, or ``None`` if the response was
    an acceptable known-error exception.
    """
    stdout = result.output or ""
    stderr = getattr(result, "stderr", "") or ""
    combined = stdout + stderr

    # 1. If CliRunner caught a known API/CLI error → acceptable
    if result.exception is not None:
        # Click usage errors (exit 2: missing required option/arg) are valid
        if isinstance(result.exception, SystemExit) and result.exit_code == 2:
            return None
        if isinstance(result.exception, KNOWN_API_ERRORS):
            return None
        # If there IS output, let validation continue (main() error handler may have fired)
        if not combined.strip():
            import traceback

            tb = "".join(
                traceback.format_exception(
                    type(result.exception), result.exception, result.exception.__traceback__
                )
            )
            pytest.fail(f"Unexpected exception:\n{tb}")

    # 2. No raw tracebacks in output
    assert "Traceback (most recent call last)" not in combined, (
        f"Unhandled traceback in output:\n{combined[:2000]}"
    )

    # 3. Parse JSON from stdout (success) or stderr (error)
    envelope: dict[str, Any] | None = None
    for source in (stdout.strip(), stderr.strip()):
        if not source:
            continue
        try:
            envelope = json.loads(source)
            break
        except json.JSONDecodeError:
            continue

    # If there's a known exception but also some output, accept it
    if (
        envelope is None
        and result.exception is not None
        and isinstance(result.exception, KNOWN_API_ERRORS)
    ):
        return None

    assert envelope is not None, (
        f"No valid JSON in output (exit={result.exit_code}).\n"
        f"stdout: {stdout[:1000]}\nstderr: {stderr[:1000]}"
    )

    # 4. Envelope shape
    assert "ok" in envelope, f"Missing 'ok' field: {list(envelope.keys())}"
    assert "command" in envelope, f"Missing 'command' field: {list(envelope.keys())}"
    assert "timestamp" in envelope, f"Missing 'timestamp' field: {list(envelope.keys())}"

    if envelope["ok"]:
        assert "data" in envelope, f"Success envelope missing 'data': {list(envelope.keys())}"
    else:
        if not allow_error:
            pytest.fail(f"Command failed with error: {envelope.get('error')}")
        assert "error" in envelope, f"Error envelope missing 'error': {list(envelope.keys())}"
        err = envelope["error"]
        assert "code" in err, f"Error body missing 'code': {err}"
        assert "message" in err, f"Error body missing 'message': {err}"

    return envelope


def assert_valid_help(stdout: str, exit_code: int) -> None:
    """Validate a ``--help`` invocation."""
    assert exit_code == 0, f"--help exited with {exit_code}: {stdout[:500]}"
    assert len(stdout) > 20, f"--help output too short: {stdout!r}"


# ---------------------------------------------------------------------------
# Parametrize data
# ---------------------------------------------------------------------------

# Vehicle read commands — need VIN and --wake
READ_VEHICLE_COMMANDS: list[tuple[str, list[str]]] = [
    ("vehicle list", ["vehicle", "list"]),
    ("vehicle get", ["vehicle", "get", VIN]),
    ("vehicle info", ["vehicle", "info", VIN]),
    ("vehicle data", ["vehicle", "data", VIN]),
    ("vehicle location", ["vehicle", "location", VIN]),
    ("vehicle mobile-access", ["vehicle", "mobile-access", VIN]),
    ("vehicle nearby-chargers", ["vehicle", "nearby-chargers", VIN]),
    ("vehicle alerts", ["vehicle", "alerts", VIN]),
    ("vehicle release-notes", ["vehicle", "release-notes", VIN]),
    ("vehicle service", ["vehicle", "service", VIN]),
    ("vehicle drivers", ["vehicle", "drivers", VIN]),
    ("vehicle subscriptions", ["vehicle", "subscriptions", VIN]),
    ("vehicle upgrades", ["vehicle", "upgrades", VIN]),
    ("vehicle options", ["vehicle", "options", VIN]),
    ("vehicle specs", ["vehicle", "specs", VIN]),
    ("vehicle warranty", ["vehicle", "warranty"]),
    ("vehicle fleet-status", ["vehicle", "fleet-status"]),
    ("vehicle telemetry config", ["vehicle", "telemetry", "config", VIN]),
    ("vehicle telemetry errors", ["vehicle", "telemetry", "errors", VIN]),
]

# Status reads — need VIN and --wake
READ_STATUS_COMMANDS: list[tuple[str, list[str]]] = [
    ("charge status", ["charge", "status", VIN]),
    ("climate status", ["climate", "status", VIN]),
    ("security status", ["security", "status", VIN]),
    ("software status", ["software", "status", VIN]),
]

# Energy reads — SITE_ID argument
READ_ENERGY_COMMANDS: list[tuple[str, list[str]]] = [
    ("energy list", ["energy", "list"]),
    ("energy status", ["energy", "status", SITE_ID]),
    ("energy tou", ["energy", "tou", SITE_ID]),
    ("energy off-grid", ["energy", "off-grid", SITE_ID]),
    ("energy grid-config", ["energy", "grid-config", SITE_ID]),
]

# Other read commands (no VIN needed, or uses account/partner scope)
READ_OTHER_COMMANDS: list[tuple[str, list[str]]] = [
    ("billing history", ["billing", "history"]),
    ("billing sessions", ["billing", "sessions"]),
    ("user me", ["user", "me"]),
    ("user region", ["user", "region"]),
    ("user orders", ["user", "orders"]),
    ("user features", ["user", "features"]),
    pytest.param(
        "sharing list-invites",
        ["sharing", "list-invites", VIN],
        marks=_requires_vin,
        id="sharing list-invites",
    ),
    ("auth status", ["auth", "status"]),
    ("key show", ["key", "show"]),
    ("key validate", ["key", "validate"]),
    ("cache status", ["cache", "status"]),
    ("status", ["status"]),
    ("partner public-key", ["partner", "public-key", "--domain", "tescmd.oceanswave.me"]),
    ("raw get /api/1/vehicles", ["raw", "get", "/api/1/vehicles"]),
]

# Help-only commands — every command that is either destructive, requires
# complex arguments, is interactive (auth login/register, setup), or is
# a write that we don't want to test live.
HELP_ONLY_COMMANDS: list[tuple[str, list[str]]] = [
    # Root
    ("tescmd", []),
    # Auth (interactive / state-changing)
    ("auth", ["auth"]),
    ("auth login", ["auth", "login"]),
    ("auth logout", ["auth", "logout"]),
    ("auth refresh", ["auth", "refresh"]),
    ("auth export", ["auth", "export"]),
    ("auth register", ["auth", "register"]),
    ("auth import", ["auth", "import"]),
    # Vehicle writes & complex args
    ("vehicle", ["vehicle"]),
    ("vehicle wake", ["vehicle", "wake"]),
    ("vehicle rename", ["vehicle", "rename"]),
    ("vehicle calendar", ["vehicle", "calendar"]),
    ("vehicle telemetry", ["vehicle", "telemetry"]),
    ("vehicle telemetry create", ["vehicle", "telemetry", "create"]),
    ("vehicle telemetry delete", ["vehicle", "telemetry", "delete"]),
    ("vehicle telemetry stream", ["vehicle", "telemetry", "stream"]),
    ("vehicle low-power", ["vehicle", "low-power"]),
    ("vehicle accessory-power", ["vehicle", "accessory-power"]),
    # Charge writes
    ("charge", ["charge"]),
    ("charge start", ["charge", "start"]),
    ("charge stop", ["charge", "stop"]),
    ("charge limit", ["charge", "limit"]),
    ("charge limit-max", ["charge", "limit-max"]),
    ("charge limit-std", ["charge", "limit-std"]),
    ("charge amps", ["charge", "amps"]),
    ("charge port-open", ["charge", "port-open"]),
    ("charge port-close", ["charge", "port-close"]),
    ("charge schedule", ["charge", "schedule"]),
    ("charge departure", ["charge", "departure"]),
    ("charge precondition-add", ["charge", "precondition-add"]),
    ("charge precondition-remove", ["charge", "precondition-remove"]),
    ("charge add-schedule", ["charge", "add-schedule"]),
    ("charge remove-schedule", ["charge", "remove-schedule"]),
    ("charge clear-schedules", ["charge", "clear-schedules"]),
    ("charge clear-preconditions", ["charge", "clear-preconditions"]),
    ("charge managed-amps", ["charge", "managed-amps"]),
    ("charge managed-location", ["charge", "managed-location"]),
    ("charge managed-schedule", ["charge", "managed-schedule"]),
    # Climate writes
    ("climate", ["climate"]),
    ("climate on", ["climate", "on"]),
    ("climate off", ["climate", "off"]),
    ("climate set", ["climate", "set"]),
    ("climate precondition", ["climate", "precondition"]),
    ("climate seat", ["climate", "seat"]),
    ("climate seat-cool", ["climate", "seat-cool"]),
    ("climate wheel-heater", ["climate", "wheel-heater"]),
    ("climate overheat", ["climate", "overheat"]),
    ("climate bioweapon", ["climate", "bioweapon"]),
    ("climate cop-temp", ["climate", "cop-temp"]),
    ("climate auto-seat", ["climate", "auto-seat"]),
    ("climate auto-wheel", ["climate", "auto-wheel"]),
    ("climate wheel-level", ["climate", "wheel-level"]),
    ("climate keeper", ["climate", "keeper"]),
    # Security writes
    ("security", ["security"]),
    ("security lock", ["security", "lock"]),
    ("security auto-secure", ["security", "auto-secure"]),
    ("security unlock", ["security", "unlock"]),
    ("security valet", ["security", "valet"]),
    ("security valet-reset", ["security", "valet-reset"]),
    ("security remote-start", ["security", "remote-start"]),
    ("security flash", ["security", "flash"]),
    ("security honk", ["security", "honk"]),
    ("security boombox", ["security", "boombox"]),
    ("security sentry", ["security", "sentry"]),
    ("security pin-to-drive", ["security", "pin-to-drive"]),
    ("security pin-reset", ["security", "pin-reset"]),
    ("security pin-clear-admin", ["security", "pin-clear-admin"]),
    ("security speed-limit", ["security", "speed-limit"]),
    ("security speed-clear", ["security", "speed-clear"]),
    ("security speed-clear-admin", ["security", "speed-clear-admin"]),
    ("security guest-mode", ["security", "guest-mode"]),
    ("security erase-data", ["security", "erase-data"]),
    # Trunk writes
    ("trunk", ["trunk"]),
    ("trunk open", ["trunk", "open"]),
    ("trunk close", ["trunk", "close"]),
    ("trunk frunk", ["trunk", "frunk"]),
    ("trunk window", ["trunk", "window"]),
    ("trunk sunroof", ["trunk", "sunroof"]),
    ("trunk tonneau-open", ["trunk", "tonneau-open"]),
    ("trunk tonneau-close", ["trunk", "tonneau-close"]),
    ("trunk tonneau-stop", ["trunk", "tonneau-stop"]),
    # Media writes
    ("media", ["media"]),
    ("media play-pause", ["media", "play-pause"]),
    ("media next-track", ["media", "next-track"]),
    ("media prev-track", ["media", "prev-track"]),
    ("media next-fav", ["media", "next-fav"]),
    ("media prev-fav", ["media", "prev-fav"]),
    ("media volume-up", ["media", "volume-up"]),
    ("media volume-down", ["media", "volume-down"]),
    ("media adjust-volume", ["media", "adjust-volume"]),
    # Nav writes
    ("nav", ["nav"]),
    ("nav send", ["nav", "send"]),
    ("nav gps", ["nav", "gps"]),
    ("nav supercharger", ["nav", "supercharger"]),
    ("nav homelink", ["nav", "homelink"]),
    ("nav waypoints", ["nav", "waypoints"]),
    # Software writes
    ("software", ["software"]),
    ("software schedule", ["software", "schedule"]),
    ("software cancel", ["software", "cancel"]),
    # Energy writes
    ("energy", ["energy"]),
    ("energy live", ["energy", "live"]),
    ("energy backup", ["energy", "backup"]),
    ("energy mode", ["energy", "mode"]),
    ("energy storm", ["energy", "storm"]),
    ("energy history", ["energy", "history"]),
    ("energy telemetry", ["energy", "telemetry"]),
    ("energy calendar", ["energy", "calendar"]),
    # Sharing writes
    ("sharing", ["sharing"]),
    ("sharing add-driver", ["sharing", "add-driver"]),
    ("sharing remove-driver", ["sharing", "remove-driver"]),
    ("sharing create-invite", ["sharing", "create-invite"]),
    ("sharing redeem-invite", ["sharing", "redeem-invite"]),
    ("sharing revoke-invite", ["sharing", "revoke-invite"]),
    # Billing (invoice needs ID)
    ("billing", ["billing"]),
    ("billing invoice", ["billing", "invoice"]),
    # Partner
    ("partner", ["partner"]),
    ("partner telemetry-error-vins", ["partner", "telemetry-error-vins"]),
    ("partner telemetry-errors", ["partner", "telemetry-errors"]),
    # Raw (post needs args)
    ("raw", ["raw"]),
    ("raw post", ["raw", "post"]),
    # Key writes
    ("key", ["key"]),
    ("key generate", ["key", "generate"]),
    ("key deploy", ["key", "deploy"]),
    ("key enroll", ["key", "enroll"]),
    ("key unenroll", ["key", "unenroll"]),
    # Cache
    ("cache", ["cache"]),
    ("cache clear", ["cache", "clear"]),
    # Setup (interactive wizard)
    ("setup", ["setup"]),
]

# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


@_requires_vin
class TestReadVehicleCommands:
    """Live reads against the vehicle — need VIN + --wake."""

    @pytest.mark.parametrize(
        ("label", "args"),
        READ_VEHICLE_COMMANDS,
        ids=[t[0] for t in READ_VEHICLE_COMMANDS],
    )
    def test_read(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
        label: str,
        args: list[str],
    ) -> None:
        result = _invoke_e2e(e2e_runner, e2e_env, args, extra_flags=["--wake"])
        assert_valid_response(result)


@_requires_vin
class TestReadStatusCommands:
    """Charge/climate/security/software status — need VIN + --wake."""

    @pytest.mark.parametrize(
        ("label", "args"),
        READ_STATUS_COMMANDS,
        ids=[t[0] for t in READ_STATUS_COMMANDS],
    )
    def test_status(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
        label: str,
        args: list[str],
    ) -> None:
        result = _invoke_e2e(e2e_runner, e2e_env, args, extra_flags=["--wake"])
        assert_valid_response(result)


@_requires_site
class TestReadEnergyCommands:
    """Energy product reads — need SITE_ID."""

    @pytest.mark.parametrize(
        ("label", "args"),
        READ_ENERGY_COMMANDS,
        ids=[t[0] for t in READ_ENERGY_COMMANDS],
    )
    def test_energy(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
        label: str,
        args: list[str],
    ) -> None:
        result = _invoke_e2e(e2e_runner, e2e_env, args)
        assert_valid_response(result)


class TestReadOtherCommands:
    """Account-level reads, billing, partner, raw, auth status, etc."""

    @pytest.mark.parametrize(
        ("label", "args"),
        READ_OTHER_COMMANDS,
        ids=[t[0] if isinstance(t, tuple) else t.id for t in READ_OTHER_COMMANDS],
    )
    def test_other(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
        label: str,
        args: list[str],
    ) -> None:
        result = _invoke_e2e(e2e_runner, e2e_env, args)
        # auth status and auth export output raw JSON (no envelope)
        if args[:2] in (["auth", "status"], ["auth", "export"]):
            combined = (result.output or "") + (getattr(result, "stderr", "") or "")
            assert "Traceback (most recent call last)" not in combined
            if result.exception and isinstance(result.exception, KNOWN_API_ERRORS):
                return
            assert result.exit_code in (0, 1)
            return
        assert_valid_response(result)


@_requires_vin
class TestBenignWriteCommands:
    """Write commands that are safe to run — with save/restore logic."""

    @staticmethod
    def _read_state(runner: CliRunner, env: dict[str, str], args: list[str]) -> dict[str, Any]:
        """Read vehicle state and parse the JSON envelope data, returning {} on failure."""
        result = _invoke_e2e(runner, env, args, extra_flags=["--wake"])
        try:
            envelope = json.loads((result.output or "").strip())
            if envelope.get("ok"):
                return envelope.get("data", {})
        except (json.JSONDecodeError, AttributeError):
            pass
        return {}

    def test_flash(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Flash lights — ephemeral, no state to restore."""
        result = _invoke_e2e(
            e2e_runner, e2e_env, ["security", "flash", VIN], extra_flags=["--wake"]
        )
        assert_valid_response(result)

    def test_honk(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Honk horn — ephemeral, no state to restore."""
        result = _invoke_e2e(
            e2e_runner, e2e_env, ["security", "honk", VIN], extra_flags=["--wake"]
        )
        assert_valid_response(result)

    def test_climate_toggle(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Toggle climate on/off and restore original state."""
        data = self._read_state(e2e_runner, e2e_env, ["climate", "status", VIN])
        cs = data.get("climate_state", {})
        originally_on = bool(cs.get("is_auto_conditioning_on", False))

        try:
            result = _invoke_e2e(
                e2e_runner, e2e_env, ["climate", "on", VIN], extra_flags=["--wake"]
            )
            assert_valid_response(result)
        finally:
            if not originally_on:
                _invoke_e2e(e2e_runner, e2e_env, ["climate", "off", VIN], extra_flags=["--wake"])

    def test_charge_port_toggle(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Toggle charge port and restore original state."""
        data = self._read_state(e2e_runner, e2e_env, ["charge", "status", VIN])
        cs = data.get("charge_state", {})
        originally_open = bool(cs.get("charge_port_door_open", False))

        try:
            result = _invoke_e2e(
                e2e_runner, e2e_env, ["charge", "port-open", VIN], extra_flags=["--wake"]
            )
            assert_valid_response(result)
        finally:
            if not originally_open:
                _invoke_e2e(
                    e2e_runner, e2e_env, ["charge", "port-close", VIN], extra_flags=["--wake"]
                )

    def test_media_volume(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Volume up then volume down to restore."""
        try:
            result = _invoke_e2e(
                e2e_runner, e2e_env, ["media", "volume-up", VIN], extra_flags=["--wake"]
            )
            assert_valid_response(result)
        finally:
            _invoke_e2e(e2e_runner, e2e_env, ["media", "volume-down", VIN], extra_flags=["--wake"])

    def test_media_play_pause(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Toggle play/pause twice to restore."""
        try:
            result = _invoke_e2e(
                e2e_runner, e2e_env, ["media", "play-pause", VIN], extra_flags=["--wake"]
            )
            assert_valid_response(result)
        finally:
            _invoke_e2e(e2e_runner, e2e_env, ["media", "play-pause", VIN], extra_flags=["--wake"])

    def test_sentry_toggle(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Toggle sentry mode and restore original state."""
        data = self._read_state(e2e_runner, e2e_env, ["security", "status", VIN])
        vs = data.get("vehicle_state", {})
        originally_on = bool(vs.get("sentry_mode", False))

        try:
            on_off = "--off" if originally_on else "--on"
            result = _invoke_e2e(
                e2e_runner,
                e2e_env,
                ["security", "sentry", VIN, on_off],
                extra_flags=["--wake"],
            )
            assert_valid_response(result)
        finally:
            restore = "--on" if originally_on else "--off"
            _invoke_e2e(
                e2e_runner,
                e2e_env,
                ["security", "sentry", VIN, restore],
                extra_flags=["--wake"],
            )

    def test_charge_limit(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Set charge limit and restore original value."""
        data = self._read_state(e2e_runner, e2e_env, ["charge", "status", VIN])
        cs = data.get("charge_state", {})
        original_limit = cs.get("charge_limit_soc", 80)

        test_limit = 75 if original_limit != 75 else 80
        try:
            result = _invoke_e2e(
                e2e_runner,
                e2e_env,
                ["charge", "limit", VIN, str(test_limit)],
                extra_flags=["--wake"],
            )
            assert_valid_response(result)
        finally:
            _invoke_e2e(
                e2e_runner,
                e2e_env,
                ["charge", "limit", VIN, str(original_limit)],
                extra_flags=["--wake"],
            )

    def test_lock_unlock(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
    ) -> None:
        """Lock/unlock and restore original state."""
        data = self._read_state(e2e_runner, e2e_env, ["security", "status", VIN])
        vs = data.get("vehicle_state", {})
        originally_locked = bool(vs.get("locked", True))

        try:
            cmd = "unlock" if originally_locked else "lock"
            result = _invoke_e2e(
                e2e_runner, e2e_env, ["security", cmd, VIN], extra_flags=["--wake"]
            )
            assert_valid_response(result)
        finally:
            restore = "lock" if originally_locked else "unlock"
            _invoke_e2e(e2e_runner, e2e_env, ["security", restore, VIN], extra_flags=["--wake"])


class TestHelpOnlyCommands:
    """Every command's --help output — verifies Click wiring, no live API."""

    @pytest.mark.parametrize(
        ("label", "args"),
        HELP_ONLY_COMMANDS,
        ids=[t[0] for t in HELP_ONLY_COMMANDS],
    )
    def test_help(
        self,
        e2e_runner: CliRunner,
        e2e_env: dict[str, str],
        label: str,
        args: list[str],
    ) -> None:
        result = e2e_runner.invoke(cli, [*args, "--help"], env=e2e_env)
        assert_valid_help(result.output, result.exit_code)
