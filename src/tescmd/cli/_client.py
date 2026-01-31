"""Shared helpers for building API clients and resolving VINs."""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

import click

from tescmd._internal.vin import resolve_vin
from tescmd.api.client import TeslaFleetClient
from tescmd.api.command import CommandAPI
from tescmd.api.energy import EnergyAPI
from tescmd.api.errors import ConfigError, KeyNotEnrolledError, TierError, VehicleAsleepError
from tescmd.api.sharing import SharingAPI
from tescmd.api.user import UserAPI
from tescmd.api.vehicle import VehicleAPI
from tescmd.auth.token_store import TokenStore
from tescmd.cache import ResponseCache
from tescmd.crypto.keys import has_key_pair, load_private_key
from tescmd.models.config import AppSettings
from tescmd.models.vehicle import VehicleData

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from rich.status import Status

    from tescmd.api.signed_command import SignedCommandAPI
    from tescmd.cli.main import AppContext
    from tescmd.output.formatter import OutputFormatter

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Respect Tesla's 3 wakes/min limit — minimum 20s between requests.
# Vehicles typically take 10-60s to establish connectivity.
# See: https://developer.tesla.com/docs/fleet-api/billing-and-limits
# ---------------------------------------------------------------------------

_WAKE_INITIAL_DELAY = 20.0
_WAKE_MAX_DELAY = 30.0
_WAKE_BACKOFF_FACTOR = 1.5


def _make_token_refresher(
    store: TokenStore, settings: AppSettings
) -> Callable[[], Awaitable[str | None]] | None:
    """Return an async callback that refreshes the access token, or *None*."""
    refresh_token = store.refresh_token
    client_id = settings.client_id
    if not refresh_token or not client_id:
        return None

    async def _refresh() -> str | None:
        from tescmd.auth.oauth import refresh_access_token

        token_data = await refresh_access_token(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=settings.client_secret,
        )
        meta = store.metadata or {}
        store.save(
            access_token=token_data.access_token,
            refresh_token=token_data.refresh_token or refresh_token,
            expires_at=time.time() + token_data.expires_in,
            scopes=meta.get("scopes", []),
            region=meta.get("region", "na"),
        )
        return token_data.access_token

    return _refresh


def _make_rate_limit_handler(
    formatter: OutputFormatter,
) -> Callable[[int, int, int], Awaitable[None]]:
    """Return an async callback that shows a countdown during rate-limit waits."""

    async def _wait(seconds: int, attempt: int, max_retries: int) -> None:
        if formatter.format != "json":
            with formatter.console.status("") as status:
                for remaining in range(seconds, 0, -1):
                    status.update(
                        f"[yellow]Rate limited — retrying in {remaining}s"
                        f" (attempt {attempt}/{max_retries})…[/yellow]"
                    )
                    await asyncio.sleep(1)
        else:
            await asyncio.sleep(seconds)

    return _wait


def get_client(app_ctx: AppContext) -> TeslaFleetClient:
    """Build an authenticated :class:`TeslaFleetClient` from settings / token store."""
    settings = AppSettings()
    store = TokenStore(profile=app_ctx.profile)

    access_token = settings.access_token
    if not access_token:
        access_token = store.access_token

    if not access_token:
        raise ConfigError(
            "No access token found. Run 'tescmd auth login' or set TESLA_ACCESS_TOKEN."
        )

    region = app_ctx.region or settings.region
    return TeslaFleetClient(
        access_token=access_token,
        region=region,
        on_token_refresh=_make_token_refresher(store, settings),
        on_rate_limit_wait=_make_rate_limit_handler(app_ctx.formatter),
    )


def get_energy_api(
    app_ctx: AppContext,
) -> tuple[TeslaFleetClient, EnergyAPI]:
    """Build a :class:`TeslaFleetClient` + :class:`EnergyAPI`."""
    client = get_client(app_ctx)
    return client, EnergyAPI(client)


def get_user_api(
    app_ctx: AppContext,
) -> tuple[TeslaFleetClient, UserAPI]:
    """Build a :class:`TeslaFleetClient` + :class:`UserAPI`."""
    client = get_client(app_ctx)
    return client, UserAPI(client)


def get_sharing_api(
    app_ctx: AppContext,
) -> tuple[TeslaFleetClient, SharingAPI]:
    """Build a :class:`TeslaFleetClient` + :class:`SharingAPI`."""
    client = get_client(app_ctx)
    return client, SharingAPI(client)


def get_vehicle_api(app_ctx: AppContext) -> tuple[TeslaFleetClient, VehicleAPI]:
    """Build a :class:`TeslaFleetClient` + :class:`VehicleAPI`."""
    client = get_client(app_ctx)
    return client, VehicleAPI(client)


def get_command_api(
    app_ctx: AppContext,
) -> tuple[TeslaFleetClient, VehicleAPI, CommandAPI | SignedCommandAPI]:
    """Build a :class:`TeslaFleetClient` + :class:`VehicleAPI` + :class:`CommandAPI`.

    When keys are available and ``command_protocol`` is not ``"unsigned"``,
    returns a :class:`SignedCommandAPI` that transparently routes signed
    commands through the Vehicle Command Protocol.
    """
    settings = AppSettings()
    client = get_client(app_ctx)
    vehicle_api = VehicleAPI(client)
    unsigned_api = CommandAPI(client)

    protocol = settings.command_protocol
    if protocol == "unsigned":
        return client, vehicle_api, unsigned_api

    key_dir = Path(settings.config_dir).expanduser() / "keys"
    if has_key_pair(key_dir) and settings.setup_tier == "full":
        from tescmd.api.signed_command import SignedCommandAPI
        from tescmd.protocol.session import SessionManager

        private_key = load_private_key(key_dir)
        session_mgr = SessionManager(private_key, client)
        return client, vehicle_api, SignedCommandAPI(client, session_mgr, unsigned_api)

    if protocol == "signed":
        raise ConfigError(
            "command_protocol is 'signed' but no key pair found or tier is not 'full'. "
            "Run 'tescmd setup' to configure full tier with key enrollment."
        )

    # protocol == "auto" with no keys → fall back to unsigned
    return client, vehicle_api, unsigned_api


def require_vin(vin_positional: str | None, vin_flag: str | None) -> str:
    """Resolve VIN or raise :class:`ConfigError`."""
    vin = resolve_vin(vin_positional=vin_positional, vin_flag=vin_flag)
    if not vin:
        raise ConfigError(
            "No VIN specified. Pass it as a positional argument, use --vin, or set TESLA_VIN."
        )
    return vin


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def get_cache(app_ctx: AppContext) -> ResponseCache:
    """Build a :class:`ResponseCache` from settings and CLI flags."""
    settings = AppSettings()
    enabled = settings.cache_enabled and not app_ctx.no_cache
    cache_dir = Path(settings.cache_dir).expanduser()
    return ResponseCache(
        cache_dir=cache_dir,
        default_ttl=settings.cache_ttl,
        enabled=enabled,
    )


async def cached_vehicle_data(
    app_ctx: AppContext,
    vehicle_api: VehicleAPI,
    vin: str,
    endpoints: list[str] | None = None,
) -> VehicleData:
    """Fetch vehicle data with caching and smart wake.

    1. Check disk cache — on hit, return immediately.
    2. On miss, check wake state cache — if recently online, try direct fetch.
    3. If direct fetch raises ``VehicleAsleepError``, fall back to ``auto_wake``.
    4. If no cached wake state, use ``auto_wake`` as normal.
    5. On success, cache the response and wake state.
    """
    formatter = app_ctx.formatter
    cache = get_cache(app_ctx)

    # 1. Cache hit
    cached = cache.get(vin, endpoints)
    if cached is not None:
        if formatter.format == "json":
            formatter.set_cache_meta(
                hit=True,
                age_seconds=cached.age_seconds,
                ttl_seconds=cached.ttl_seconds,
            )
        else:
            formatter.rich.info(
                f"[dim]Data cached {cached.age_seconds}s ago"
                f" (TTL {cached.ttl_seconds}s)."
                f" Use --fresh for live data.[/dim]"
            )
        return VehicleData.model_validate(cached.data)

    # 2. Smart wake — skip wake overhead if vehicle was recently online
    if cache.get_wake_state(vin):
        try:
            vdata = await vehicle_api.get_vehicle_data(vin, endpoints=endpoints)
            cache.put(vin, vdata.model_dump(), endpoints)
            cache.put_wake_state(vin, "online")
            return vdata
        except VehicleAsleepError:
            pass  # Fall through to full auto_wake

    # 3. Full auto_wake path
    vdata = await auto_wake(
        formatter,
        vehicle_api,
        vin,
        lambda: vehicle_api.get_vehicle_data(vin, endpoints=endpoints),
        auto=app_ctx.auto_wake,
    )
    cache.put(vin, vdata.model_dump(), endpoints)
    cache.put_wake_state(vin, "online")
    return vdata


def _check_signing_requirement(
    cmd_api: CommandAPI | SignedCommandAPI,
    command_name: str,
    settings: AppSettings,
) -> None:
    """Raise a clear error when a signing-required command would silently fall back to unsigned.

    VCSEC commands (lock, unlock, trunk, window, remote_start) require the
    Vehicle Command Protocol.  If keys are missing and ``command_protocol``
    is ``"auto"``, the code falls back to ``CommandAPI`` (unsigned REST),
    which will fail with a confusing API error.  This guard catches that
    case early and gives actionable guidance.
    """
    from tescmd.api.signed_command import SignedCommandAPI as _SignedAPI
    from tescmd.protocol.commands import get_command_spec
    from tescmd.protocol.protobuf.messages import Domain

    if isinstance(cmd_api, _SignedAPI):
        return  # Already signed — nothing to guard

    if settings.command_protocol == "unsigned":
        return  # User explicitly chose unsigned — respect the override

    spec = get_command_spec(command_name)
    if spec is None or not spec.requires_signing:
        return  # Unsigned command — no issue

    if spec.domain == Domain.DOMAIN_VEHICLE_SECURITY:
        key_dir = Path(settings.config_dir).expanduser() / "keys"
        if not has_key_pair(key_dir):
            raise ConfigError(
                "This command requires a signed channel (Vehicle Command Protocol) "
                "but no EC key pair was found. "
                "Run 'tescmd key generate' then 'tescmd key deploy' and 'tescmd key enroll'."
            )
        raise KeyNotEnrolledError(
            "This command requires a signed channel but the key is not active. "
            "Enroll via 'tescmd key enroll' and approve in the Tesla app.",
            status_code=422,
        )


async def execute_command(
    app_ctx: AppContext,
    vin_positional: str | None,
    method_name: str,
    cmd_name: str,
    body: dict[str, Any] | None = None,
    *,
    success_message: str = "",
) -> None:
    """Shared helper for simple vehicle commands (POST, no read data).

    Resolves the VIN, obtains a :class:`CommandAPI`, calls *method_name* with
    ``auto_wake``, invalidates the cache, and outputs the result.
    """
    # Tier enforcement — readonly tier cannot execute write commands
    settings = AppSettings()
    if settings.setup_tier == "readonly":
        raise TierError("This command requires 'full' tier setup. Run 'tescmd setup' to upgrade.")

    formatter = app_ctx.formatter
    vin = require_vin(vin_positional, app_ctx.vin)
    client, vehicle_api, cmd_api = get_command_api(app_ctx)

    # Guard: VCSEC commands require signed channel — don't silently fall back
    _check_signing_requirement(cmd_api, method_name, settings)

    try:
        method = getattr(cmd_api, method_name)
        result = await auto_wake(
            formatter,
            vehicle_api,
            vin,
            lambda: method(vin, **body) if body else method(vin),
            auto=app_ctx.auto_wake,
        )
    finally:
        await client.close()

    invalidate_cache_for_vin(app_ctx, vin)

    if formatter.format == "json":
        formatter.output(result, command=cmd_name)
    else:
        msg = result.response.reason or success_message
        formatter.rich.command_result(result.response.result, msg)


def invalidate_cache_for_vin(app_ctx: AppContext, vin: str) -> None:
    """Clear cached data for *vin* (called after state-changing commands)."""
    cache = get_cache(app_ctx)
    cache.clear(vin)


# ---------------------------------------------------------------------------
# Auto-wake helper
# ---------------------------------------------------------------------------


async def auto_wake(
    formatter: OutputFormatter,
    vehicle_api: VehicleAPI,
    vin: str,
    operation: Callable[[], Awaitable[T]],
    *,
    timeout: int = 90,
    auto: bool = False,
) -> T:
    """Run *operation*; if the vehicle is asleep, wake it and retry.

    When *auto* is ``False`` (default) and the output is a TTY, the user
    is prompted before sending a billable wake API call.  In JSON / piped
    mode without *auto*, a ``VehicleAsleepError`` is raised immediately.

    Pass ``auto=True`` (via ``--wake`` flag) to skip the prompt.
    """
    try:
        return await operation()
    except VehicleAsleepError:
        pass

    # Vehicle is asleep — decide whether to wake.
    if not auto:
        if formatter.format not in ("json",):
            # Interactive TTY prompt with retry loop
            while True:
                formatter.rich.info("")
                formatter.rich.info("[yellow]Vehicle is asleep.[/yellow]")
                formatter.rich.info("")
                formatter.rich.info(
                    "  Waking via the Tesla app (iOS/Android) is [green]free[/green]."
                )
                formatter.rich.info("  Sending a wake via the API is [yellow]billable[/yellow].")
                formatter.rich.info("")
                choice = click.prompt(
                    "  [W] Wake via API    [R] Retry    [C] Cancel",
                    type=click.Choice(["w", "r", "c"], case_sensitive=False),
                    default="c",
                    show_choices=False,
                )
                if choice.lower() == "r":
                    try:
                        return await operation()
                    except VehicleAsleepError:
                        continue  # Still asleep — show prompt again
                if choice.lower() == "w":
                    break  # Fall through to wake-via-API path
                # choice == "c"
                raise VehicleAsleepError(
                    "Wake cancelled. You can wake the vehicle from the"
                    " Tesla app for free and re-run the command.",
                    status_code=408,
                )
        else:
            # JSON / piped mode — no interactive prompt possible
            raise VehicleAsleepError(
                "Vehicle is asleep. Use --wake to send a billable wake via the API,"
                " or wake from the Tesla app for free and re-run the command.",
                status_code=408,
            )

    # Proceed with wake.
    if formatter.format not in ("json",):
        with formatter.console.status("", spinner="dots") as status:
            await _wake_and_wait(vehicle_api, vin, timeout, status=status)
        formatter.rich.info("[green]Vehicle is awake.[/green]")
    else:
        await _wake_and_wait(vehicle_api, vin, timeout)

    # Retry the original operation.
    return await operation()


async def _wake_and_wait(
    vehicle_api: VehicleAPI,
    vin: str,
    timeout: int,
    *,
    status: Status | None = None,
) -> None:
    """Send a wake command and poll until the vehicle is online.

    Uses exponential backoff starting at 20s (capped at 30s) to respect
    Tesla's 3 wakes/min rate limit.  RateLimitError (429) is handled
    transparently by the client-level retry loop.
    """
    vehicle = await vehicle_api.wake(vin)
    start = time.monotonic()
    deadline = start + timeout
    delay = _WAKE_INITIAL_DELAY

    while time.monotonic() < deadline and vehicle.state != "online":
        # Countdown within each delay interval (1s ticks for UI updates).
        sleep_until = time.monotonic() + delay
        while time.monotonic() < sleep_until:
            if status:
                elapsed = int(time.monotonic() - start)
                status.update(
                    f"[bold yellow]Vehicle is asleep — waking up… ({elapsed}s)[/bold yellow]"
                )
            await asyncio.sleep(1)

        delay = min(delay * _WAKE_BACKOFF_FACTOR, _WAKE_MAX_DELAY)
        with contextlib.suppress(VehicleAsleepError):
            vehicle = await vehicle_api.wake(vin)

    if vehicle.state != "online":
        raise VehicleAsleepError(
            f"Vehicle did not wake within {timeout}s. Try again later.",
            status_code=408,
        )
