"""CLI command for the tiered onboarding wizard (``tescmd setup``)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._options import global_options
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext
    from tescmd.output.formatter import OutputFormatter

# Callable signature for ``formatter.rich.info`` (and mocks in tests).
_InfoFn = Callable[..., object]

TIER_READONLY = "readonly"
TIER_FULL = "full"


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("setup")
@global_options
def setup_cmd(app_ctx: AppContext) -> None:
    """Interactive setup wizard for first-time configuration."""
    run_async(_cmd_setup(app_ctx))


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------


async def _cmd_setup(app_ctx: AppContext) -> None:
    """Run the tiered onboarding wizard."""
    formatter = app_ctx.formatter
    settings = AppSettings()

    # Phase 0: Welcome + tier selection
    tier = _prompt_tier(formatter, settings)
    if not tier:
        return

    # Phase 1: Domain setup via GitHub Pages (must happen before developer
    # portal because Tesla requires the Allowed Origin URL to match the
    # registration domain)
    domain = _domain_setup(formatter, settings)
    if not domain:
        return

    # Re-read settings after potential .env changes
    settings = AppSettings()

    # Phase 2: Developer portal walkthrough (credentials — uses domain for
    # the Allowed Origin URL instructions)
    client_id, client_secret = _developer_portal_setup(formatter, app_ctx, settings, domain=domain)
    if not client_id:
        return

    # Re-read settings again
    settings = AppSettings()

    # Phase 3: Key generation + deployment (full tier only)
    if tier == TIER_FULL:
        _key_setup(formatter, settings, domain)

    # Phase 3.5: Key enrollment (full tier only)
    if tier == TIER_FULL:
        await _enrollment_step(formatter, app_ctx, settings)

    # Phase 4: Fleet API partner registration
    await _registration_step(formatter, app_ctx, settings, client_id, client_secret, domain)

    # Phase 5: OAuth login
    await _oauth_login_step(formatter, app_ctx, settings, client_id, client_secret)

    # Phase 6: Summary
    _print_next_steps(formatter, tier)


# ---------------------------------------------------------------------------
# Phase 0: Tier selection
# ---------------------------------------------------------------------------


def _prompt_tier(formatter: OutputFormatter, settings: AppSettings) -> str:
    """Ask the user which tier they want and persist the choice."""
    info = formatter.rich.info

    # If already configured, offer to keep or change
    existing_tier = settings.setup_tier
    if existing_tier in (TIER_READONLY, TIER_FULL):
        info(f"Setup tier: [cyan]{existing_tier}[/cyan] (previously configured)")
        info("")

        if existing_tier == TIER_FULL:
            return existing_tier

        # Offer upgrade from readonly → full
        try:
            answer = input("Upgrade to full control? [y/N] ").strip()
        except (EOFError, KeyboardInterrupt):
            info("")
            return ""

        if answer.lower() != "y":
            return existing_tier

        tier = TIER_FULL
    else:
        info("")
        info("[bold cyan]Welcome to tescmd![/bold cyan]")
        info("")
        info("How would you like to use tescmd?")
        info("")
        info(
            "  [bold]1.[/bold] [cyan]Read-only[/cyan]"
            " — view vehicle data, location, battery status"
        )
        info("     (Requires: Tesla Developer app + domain for registration)")
        info("")
        info(
            "  [bold]2.[/bold] [cyan]Full control[/cyan]"
            " — read data + lock/unlock, charge, climate, etc."
        )
        info("     (Requires: all of the above + EC key pair deployed to your domain)")
        info(
            "     [dim]Enables Fleet Telemetry streaming — up to 97% cost"
            " reduction vs polling the REST API.[/dim]"
        )
        info("")

        try:
            choice = input("Choose [1] or [2] (default: 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            info("")
            return ""

        tier = TIER_FULL if choice == "2" else TIER_READONLY

    # Persist tier
    from tescmd.cli.auth import _write_env_value

    _write_env_value("TESLA_SETUP_TIER", tier)
    info(f"[green]Tier set to: {tier}[/green]")
    info("")

    return tier


# ---------------------------------------------------------------------------
# Phase 2: Developer portal walkthrough
# ---------------------------------------------------------------------------


def _developer_portal_setup(
    formatter: OutputFormatter,
    app_ctx: AppContext,
    settings: AppSettings,
    *,
    domain: str = "",
) -> tuple[str, str]:
    """Walk through Tesla Developer Portal setup if credentials are missing."""
    info = formatter.rich.info

    client_id = settings.client_id
    client_secret = settings.client_secret

    if client_id:
        info(f"Client ID: [cyan]{client_id[:8]}...[/cyan] (already configured)")
        return (client_id, client_secret or "")

    info("[bold]Phase 2: Tesla Developer Portal Setup[/bold]")
    info("")

    # Detect Tailscale hostname if domain was set to Tailscale in Phase 1
    ts_hostname = ""
    if settings.hosting_method == "tailscale" and settings.domain:
        ts_hostname = settings.domain

    # Delegate to the existing interactive setup wizard, passing the domain
    # so the portal instructions show the correct Allowed Origin URL
    from tescmd.models.auth import DEFAULT_PORT

    port = DEFAULT_PORT
    redirect_uri = f"http://localhost:{port}/callback"
    from tescmd.cli.auth import _interactive_setup

    return _interactive_setup(
        formatter, port, redirect_uri, domain=domain, tailscale_hostname=ts_hostname
    )


# ---------------------------------------------------------------------------
# Phase 1: Domain setup
# ---------------------------------------------------------------------------


def _domain_setup(formatter: OutputFormatter, settings: AppSettings) -> str:
    """Set up a domain via GitHub Pages, Tailscale Funnel, or manual entry."""
    info = formatter.rich.info

    if settings.domain:
        info(f"Domain: [cyan]{settings.domain}[/cyan] (already configured)")
        info("")
        return settings.domain

    info("[bold]Phase 1: Domain Setup[/bold]")
    info("")
    info("Tesla requires a registered domain for Fleet API access.")
    info("")

    # Priority 1: GitHub Pages (always-on hosting)
    from tescmd.deploy.github_pages import is_gh_authenticated, is_gh_available

    if is_gh_available() and is_gh_authenticated():
        return _automated_domain_setup(formatter, settings)

    # Priority 2: Tailscale Funnel (requires local machine running)
    if run_async(_is_tailscale_ready()):
        return _tailscale_domain_setup(formatter, settings)

    # Priority 3: Manual
    return _manual_domain_setup(formatter)


async def _is_tailscale_ready() -> bool:
    """Wrapper to check Tailscale readiness without raising."""
    from tescmd.deploy.tailscale_serve import is_tailscale_serve_ready

    return await is_tailscale_serve_ready()


def _automated_domain_setup(formatter: OutputFormatter, settings: AppSettings) -> str:
    """Offer to auto-create a GitHub Pages site."""
    info = formatter.rich.info

    from tescmd.deploy.github_pages import (
        create_pages_repo,
        get_gh_username,
        get_pages_domain,
    )

    username = get_gh_username()
    suggested_domain = f"{username}.github.io".lower()

    info(f"GitHub CLI detected. Logged in as [cyan]{username}[/cyan].")
    info(f"Suggested domain: [cyan]{suggested_domain}[/cyan]")
    info("")
    info("[dim]Note: GitHub Pages provides always-on key hosting but cannot[/dim]")
    info("[dim]serve as a Fleet Telemetry server. If you plan to use telemetry[/dim]")
    info("[dim]streaming, choose Tailscale instead (install Tailscale, then[/dim]")
    info("[dim]re-run setup).[/dim]")
    info("")

    try:
        answer = input(f"Create/use {suggested_domain} as your domain? [Y/n] ").strip()
    except (EOFError, KeyboardInterrupt):
        info("")
        return ""

    if answer.lower() == "n":
        return _manual_domain_setup(formatter)

    info("Creating GitHub Pages repo...")
    repo_name = create_pages_repo(username)
    domain = get_pages_domain(repo_name)

    # Persist domain and repo to .env
    from tescmd.cli.auth import _write_env_value

    _write_env_value("TESLA_DOMAIN", domain)
    _write_env_value("TESLA_GITHUB_REPO", repo_name)

    info(f"[green]Domain configured: {domain}[/green]")
    info(f"[green]GitHub repo: {repo_name}[/green]")
    info("")

    return domain


def _tailscale_domain_setup(formatter: OutputFormatter, settings: AppSettings) -> str:
    """Offer to use Tailscale Funnel for key hosting."""
    info = formatter.rich.info

    from tescmd.telemetry.tailscale import TailscaleManager

    hostname: str = run_async(TailscaleManager().get_hostname())

    info("Tailscale detected. Your key would be hosted at:")
    info(f"  [cyan]https://{hostname}/{_WELL_KNOWN_PATH}[/cyan]")
    info("")
    info("[yellow]Important:[/yellow] Tailscale Funnel requires your machine to be running.")
    info("If your machine is off or Tailscale stops, Tesla cannot reach your")
    info("public key. This is fine for development and testing.")
    info("For always-on hosting, use GitHub Pages instead (install gh CLI).")
    info("")
    info("[green]Telemetry streaming:[/green] If you plan to use Fleet Telemetry")
    info("streaming (tescmd vehicle telemetry stream), you should use your")
    info("Tailscale hostname as your domain. Tesla requires the telemetry")
    info("server hostname to match your registered domain.")
    info("")

    try:
        answer = input(f"Use {hostname} as your domain? [Y/n] ").strip()
    except (EOFError, KeyboardInterrupt):
        info("")
        return ""

    if answer.lower() == "n":
        return _manual_domain_setup(formatter)

    domain = hostname

    # Persist domain and hosting method to .env
    from tescmd.cli.auth import _write_env_value

    _write_env_value("TESLA_DOMAIN", domain)
    _write_env_value("TESLA_HOSTING_METHOD", "tailscale")

    info(f"[green]Domain configured: {domain}[/green]")
    info("[green]Hosting method: Tailscale Funnel[/green]")
    info("")

    return domain


# Well-known path constant (shared with deploy modules)
_WELL_KNOWN_PATH = ".well-known/appspecific/com.tesla.3p.public-key.pem"


def _manual_domain_setup(formatter: OutputFormatter) -> str:
    """Prompt for a domain manually."""
    from tescmd.cli.auth import _prompt_for_domain

    return _prompt_for_domain(formatter)


# ---------------------------------------------------------------------------
# Phase 3: Key generation + deployment
# ---------------------------------------------------------------------------


def _key_setup(formatter: OutputFormatter, settings: AppSettings, domain: str) -> None:
    """Generate keys and deploy via the configured hosting method (full tier only)."""
    info = formatter.rich.info

    info("[bold]Phase 3: EC Key Generation & Deployment[/bold]")
    info("")

    key_dir = Path(settings.config_dir).expanduser() / "keys"

    from tescmd.crypto.keys import (
        generate_ec_key_pair,
        get_key_fingerprint,
        has_key_pair,
    )

    # Generate keys if needed
    if has_key_pair(key_dir):
        info(f"Key pair: [cyan]exists[/cyan] (fingerprint: {get_key_fingerprint(key_dir)})")
    else:
        info("Generating EC P-256 key pair...")
        generate_ec_key_pair(key_dir)
        info("[green]Key pair generated.[/green]")
        info(f"  Fingerprint: {get_key_fingerprint(key_dir)}")

    info("")

    # Branch on hosting method
    hosting = settings.hosting_method

    if hosting == "tailscale":
        _deploy_key_tailscale(formatter, settings, key_dir, domain)
    else:
        _deploy_key_github(formatter, settings, key_dir, domain)


def _deploy_key_tailscale(
    formatter: OutputFormatter,
    settings: AppSettings,
    key_dir: Path,
    domain: str,
) -> None:
    """Deploy key via Tailscale Funnel."""
    info = formatter.rich.info

    from tescmd.crypto.keys import load_public_key_pem
    from tescmd.deploy.tailscale_serve import (
        deploy_public_key_tailscale,
        get_key_url,
        start_key_serving,
        validate_tailscale_key_url,
        wait_for_tailscale_deployment,
    )

    # Check if key is already deployed
    if run_async(validate_tailscale_key_url(domain)):
        info(f"Public key: [green]already accessible[/green] at {get_key_url(domain)}")
        info("")
        return

    info("Deploying public key via Tailscale Funnel...")
    pem = load_public_key_pem(key_dir)
    run_async(deploy_public_key_tailscale(pem))
    run_async(start_key_serving())

    info("[green]Tailscale serve + Funnel started.[/green]")
    info("Waiting for key to become accessible...")

    deployed = run_async(wait_for_tailscale_deployment(domain))
    if deployed:
        info(f"[green]Key is live at:[/green] {get_key_url(domain)}")
    else:
        info(
            "[yellow]Key deployed but not yet accessible."
            " Tailscale Funnel may still be propagating.[/yellow]"
        )
        info("  Run [cyan]tescmd key validate[/cyan] to check later.")
    info("")


def _deploy_key_github(
    formatter: OutputFormatter,
    settings: AppSettings,
    key_dir: Path,
    domain: str,
) -> None:
    """Deploy key via GitHub Pages."""
    info = formatter.rich.info

    from tescmd.crypto.keys import load_public_key_pem
    from tescmd.deploy.github_pages import (
        deploy_public_key,
        fetch_key_pem,
        get_key_url,
        is_gh_authenticated,
        is_gh_available,
        wait_for_pages_deployment,
    )

    github_repo = settings.github_repo
    if not github_repo:
        info("[yellow]No GitHub repo configured for key deployment.[/yellow]")
        info("  Run [cyan]tescmd key deploy[/cyan] to deploy your public key.")
        info("")
        return

    if not (is_gh_available() and is_gh_authenticated()):
        info("[yellow]GitHub CLI not available or not authenticated.[/yellow]")
        info("  Run [cyan]tescmd key deploy[/cyan] after setting up gh CLI.")
        info("")
        return

    # Compare remote key to local key
    pem = load_public_key_pem(key_dir)
    remote_pem = fetch_key_pem(domain)

    if remote_pem is not None and remote_pem == pem.strip():
        info(f"Public key: [green]matches GitHub[/green] at {get_key_url(domain)}")
        info("")
        return

    if remote_pem is not None:
        # Remote key exists but differs — confirm before overwriting
        info("[yellow]The public key on GitHub differs from your local key.[/yellow]")
        info(f"  Remote: {get_key_url(domain)}")
        info("  This can happen after regenerating your key pair.")
        info("")
        try:
            answer = input("Update GitHub with the local key? [y/N] ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer.lower() != "y":
            info("[dim]Skipped — GitHub key left unchanged.[/dim]")
            info("")
            return
        info("Updating public key on GitHub Pages...")
    else:
        info("Deploying public key to GitHub Pages...")

    deploy_public_key(pem, github_repo)

    info("[green]Key committed and pushed.[/green]")
    info("Waiting for GitHub Pages to publish...")

    deployed = wait_for_pages_deployment(domain)
    if deployed:
        info(f"[green]Key is live at:[/green] {get_key_url(domain)}")
    else:
        info(
            "[yellow]Key deployed but not yet accessible."
            " GitHub Pages may still be building.[/yellow]"
        )
        info("  Run [cyan]tescmd key validate[/cyan] to check later.")
    info("")


# ---------------------------------------------------------------------------
# Phase 3.5: Key enrollment
# ---------------------------------------------------------------------------


async def _enrollment_step(
    formatter: OutputFormatter,
    app_ctx: AppContext,
    settings: AppSettings,
) -> None:
    """Guide the user through key enrollment via the Tesla app portal."""
    import webbrowser

    from tescmd.crypto.keys import get_key_fingerprint, has_key_pair

    info = formatter.rich.info
    key_dir = Path(settings.config_dir).expanduser() / "keys"

    if not has_key_pair(key_dir):
        return  # No keys to enroll

    domain = settings.domain
    if not domain:
        info("[yellow]No domain configured — skipping enrollment.[/yellow]")
        info("  Run [cyan]tescmd key enroll[/cyan] after setting TESLA_DOMAIN.")
        info("")
        return

    info("[bold]Phase 3.5: Key Enrollment[/bold]")
    info("")
    info("  Your key is generated and deployed. To control a vehicle, the key")
    info("  must also be enrolled via the Tesla app.")
    info("")

    # Verify the public key is accessible (method-aware)
    if settings.hosting_method == "tailscale":
        from tescmd.deploy.tailscale_serve import get_key_url
        from tescmd.deploy.tailscale_serve import (
            validate_tailscale_key_url as _validate,
        )

        key_url = get_key_url(domain)
        key_accessible = await _validate(domain)
    else:
        from tescmd.deploy.github_pages import get_key_url as gh_get_key_url
        from tescmd.deploy.github_pages import validate_key_url

        key_url = gh_get_key_url(domain)
        key_accessible = validate_key_url(domain)
    if not key_accessible:
        info(f"  [yellow]Public key not accessible at {key_url}[/yellow]")
        info("  Enrollment requires the key to be live. Skipping for now.")
        info("  After deploying, run [cyan]tescmd key enroll[/cyan].")
        info("")
        return

    fingerprint = get_key_fingerprint(key_dir)
    enroll_url = f"https://tesla.com/_ak/{domain}"

    info(f"  Domain:      {domain}")
    info(f"  Fingerprint: {fingerprint[:8]}…")
    info(f"  Public key:  [green]accessible[/green] at {key_url}")
    info("")

    try:
        answer = input("  Open enrollment URL in your browser? [Y/n] ").strip()
    except (EOFError, KeyboardInterrupt):
        info("")
        return

    if answer.lower() not in ("n", "no"):
        info("")
        info(f"  Opening [link={enroll_url}]{enroll_url}[/link]…")
        webbrowser.open(enroll_url)
        info("")

    info("  " + "━" * 49)
    info("    [bold yellow]ACTION REQUIRED: Add virtual key in the Tesla app[/bold yellow]")
    info("")
    info(f"    Enrollment URL: {enroll_url}")
    info("")
    info("    1. Open the URL above [bold]on your phone[/bold]")
    info("    2. Tap [bold]Finish Setup[/bold] on the web page")
    info("    3. The Tesla app shows an [bold]Add Virtual Key[/bold] prompt")
    info("    4. Approve it")
    info("")
    info("    [dim]If the prompt doesn't appear, force-quit the Tesla app,[/dim]")
    info("    [dim]go back to your browser, and tap Finish Setup again.[/dim]")
    info("  " + "━" * 49)
    info("")
    info("  After approving, try: [cyan]tescmd charge status --wake[/cyan]")
    info("")


# ---------------------------------------------------------------------------
# Phase 4: Fleet API registration
# ---------------------------------------------------------------------------


async def _registration_step(
    formatter: OutputFormatter,
    app_ctx: AppContext,
    settings: AppSettings,
    client_id: str,
    client_secret: str,
    domain: str,
) -> None:
    """Register with the Tesla Fleet API."""
    info = formatter.rich.info

    if not client_secret:
        info("[yellow]Skipping Fleet API registration (no client secret).[/yellow]")
        info("  Run [cyan]tescmd auth register[/cyan] after adding TESLA_CLIENT_SECRET.")
        info("")
        return

    info("[bold]Phase 4: Fleet API Registration[/bold]")
    info("")

    # Pre-check: Tesla requires the public key to be accessible before
    # registration will succeed (HTTP 424 otherwise).
    key_ready = _precheck_public_key(formatter, settings, domain)
    if not key_ready:
        info("[yellow]Skipping registration — public key not accessible.[/yellow]")
        info("  Run [cyan]tescmd auth register[/cyan] once the key is live.")
        info("")
        return

    from tescmd.auth.oauth import register_partner_account

    region = app_ctx.region or settings.region

    info(f"Registering with Fleet API ({region} region)...")
    try:
        _result, _scopes = await register_partner_account(
            client_id=client_id,
            client_secret=client_secret,
            domain=domain,
            region=region,
        )
        if _result.get("already_registered"):
            info("[green]Already registered — no action needed.[/green]")
        else:
            info("[green]Registration successful.[/green]")
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        exc_text = str(exc)

        if status_code == 412 or "must match registered allowed origin" in exc_text:
            _remediate_412(info, domain)
        elif status_code == 424 or "Public key download failed" in exc_text:
            _remediate_424(info, domain)
        else:
            info(f"[yellow]Registration failed:[/yellow] {exc}")
            info("  Run [cyan]tescmd auth register[/cyan] to retry.")
    info("")


def _precheck_public_key(
    formatter: OutputFormatter,
    settings: AppSettings,
    domain: str,
) -> bool:
    """Verify the public key is accessible; offer to deploy if not.

    Returns True when the key is confirmed live (or was already live),
    False when the user declines or deployment/validation fails.
    """
    info = formatter.rich.info

    info("Checking public key availability...")

    # Check accessibility via the appropriate method
    if settings.hosting_method == "tailscale":
        from tescmd.deploy.tailscale_serve import (
            get_key_url,
            validate_tailscale_key_url,
        )

        key_url = get_key_url(domain)
        accessible = run_async(validate_tailscale_key_url(domain))
    else:
        from tescmd.deploy.github_pages import get_key_url as gh_get_key_url
        from tescmd.deploy.github_pages import validate_key_url

        key_url = gh_get_key_url(domain)
        accessible = validate_key_url(domain)

    if accessible:
        info(f"  Public key: [green]accessible[/green] at {key_url}")
        info("")
        return True

    info(f"  Public key: [yellow]not found[/yellow] at {key_url}")
    info("")
    info("  Tesla requires your public key to be accessible before registration will succeed.")
    info("")

    # Offer to automate key generation + deployment
    try:
        answer = input("Generate and deploy the public key now? [Y/n] ").strip()
    except (EOFError, KeyboardInterrupt):
        info("")
        return False

    if answer.lower() == "n":
        _remediate_424(info, domain)
        return False

    # Automate: generate (if needed) + deploy + wait
    return _auto_deploy_key(formatter, settings, domain)


def _auto_deploy_key(
    formatter: OutputFormatter,
    settings: AppSettings,
    domain: str,
) -> bool:
    """Generate a key pair (if needed), deploy via configured method, and wait.

    Returns True when the key is confirmed accessible, False otherwise.
    """
    info = formatter.rich.info
    key_dir = Path(settings.config_dir).expanduser() / "keys"

    from tescmd.crypto.keys import (
        generate_ec_key_pair,
        get_key_fingerprint,
        has_key_pair,
    )

    # 1. Generate keys if needed
    if has_key_pair(key_dir):
        info(f"Key pair: [cyan]exists[/cyan] (fingerprint: {get_key_fingerprint(key_dir)})")
    else:
        info("Generating EC P-256 key pair...")
        generate_ec_key_pair(key_dir)
        info(f"[green]Key pair generated.[/green] Fingerprint: {get_key_fingerprint(key_dir)}")
    info("")

    # 2. Deploy via the appropriate method
    if settings.hosting_method == "tailscale":
        return _auto_deploy_key_tailscale(info, key_dir, domain)
    return _auto_deploy_key_github(info, settings, key_dir, domain)


def _auto_deploy_key_tailscale(
    info: _InfoFn,
    key_dir: Path,
    domain: str,
) -> bool:
    """Deploy key via Tailscale Funnel and wait."""
    from tescmd.crypto.keys import load_public_key_pem
    from tescmd.deploy.tailscale_serve import (
        deploy_public_key_tailscale,
        get_key_url,
        start_key_serving,
        validate_tailscale_key_url,
        wait_for_tailscale_deployment,
    )

    # Already deployed?
    if run_async(validate_tailscale_key_url(domain)):
        info(f"Public key: [green]already accessible[/green] at {get_key_url(domain)}")
        info("")
        return True

    info("Deploying public key via Tailscale Funnel...")
    pem = load_public_key_pem(key_dir)
    run_async(deploy_public_key_tailscale(pem))
    run_async(start_key_serving())

    info("[green]Tailscale serve + Funnel started.[/green]")
    info("Waiting for key to become accessible...")

    deployed = run_async(wait_for_tailscale_deployment(domain))
    if deployed:
        info(f"[green]Key is live at:[/green] {get_key_url(domain)}")
        info("")
        return True

    info("[yellow]Key deployed but not yet accessible.[/yellow]")
    info(
        "  Run [cyan]tescmd key validate[/cyan] to check, then [cyan]tescmd auth register[/cyan]."
    )
    info("")
    return False


def _auto_deploy_key_github(
    info: _InfoFn,
    settings: AppSettings,
    key_dir: Path,
    domain: str,
) -> bool:
    """Deploy key via GitHub Pages and wait."""
    from tescmd.crypto.keys import load_public_key_pem
    from tescmd.deploy.github_pages import (
        deploy_public_key,
        get_key_url,
        is_gh_authenticated,
        is_gh_available,
        validate_key_url,
        wait_for_pages_deployment,
    )

    github_repo = settings.github_repo
    if not github_repo:
        info("[yellow]No GitHub repo configured for key deployment.[/yellow]")
        info("  Run [cyan]tescmd key deploy[/cyan] to deploy your public key.")
        info("")
        return False

    if not (is_gh_available() and is_gh_authenticated()):
        info("[yellow]GitHub CLI not available or not authenticated.[/yellow]")
        info("  Run [cyan]tescmd key deploy[/cyan] after setting up gh CLI.")
        info("")
        return False

    # Already deployed?
    if validate_key_url(domain):
        info(f"Public key: [green]already accessible[/green] at {get_key_url(domain)}")
        info("")
        return True

    info("Deploying public key to GitHub Pages...")
    pem = load_public_key_pem(key_dir)
    deploy_public_key(pem, github_repo)

    info("[green]Key committed and pushed.[/green]")
    info("Waiting for GitHub Pages to publish...")

    deployed = wait_for_pages_deployment(domain)
    if deployed:
        info(f"[green]Key is live at:[/green] {get_key_url(domain)}")
        info("")
        return True

    info(
        "[yellow]Key deployed but not yet accessible. GitHub Pages may still be building.[/yellow]"
    )
    info(
        "  Run [cyan]tescmd key validate[/cyan] to check, then [cyan]tescmd auth register[/cyan]."
    )
    info("")
    return False


def _remediate_412(info: _InfoFn, domain: str) -> None:
    """Print remediation steps for HTTP 412 (origin mismatch)."""
    info("[yellow]Registration failed (HTTP 412): origin mismatch.[/yellow]")
    info("")
    info("[bold]How to fix:[/bold]")
    info(
        "  The [cyan]Allowed Origin URL[/cyan] in your Tesla Developer"
        " app must match your registration domain."
    )
    info("")
    info("  1. Go to [cyan]https://developer.tesla.com[/cyan]")
    info("  2. Open your application")
    info("  3. Set [cyan]Allowed Origin URL[/cyan] to:")
    info(f"     [bold]https://{domain}[/bold]")
    info(
        "     [dim]For telemetry streaming, also add your Tailscale origin"
        " (e.g. https://<machine>.tailnet.ts.net)[/dim]"
    )
    info("  4. Save, then re-run [cyan]tescmd setup[/cyan]")


def _remediate_424(info: _InfoFn, domain: str) -> None:
    """Print remediation steps for HTTP 424 (public key not found)."""
    from tescmd.deploy.github_pages import WELL_KNOWN_PATH

    key_url = f"https://{domain}/{WELL_KNOWN_PATH}"

    info("[yellow]Registration failed (HTTP 424): public key not found.[/yellow]")
    info("")
    info("[bold]How to fix:[/bold]")
    info("  Tesla tried to download your public key during registration but got a 404.")
    info(f"  Expected URL: [cyan]{key_url}[/cyan]")
    info("")
    info("  1. Generate a key pair (if you haven't already):")
    info("     [cyan]tescmd key generate[/cyan]")
    info("")
    info("  2. Deploy the public key to your domain:")
    info("     [cyan]tescmd key deploy[/cyan]")
    info("")
    info("  3. Verify the key is accessible:")
    info("     [cyan]tescmd key validate[/cyan]")
    info("")
    info(
        "  4. Once the key is live, re-run [cyan]tescmd setup[/cyan]"
        " (or [cyan]tescmd auth register[/cyan])."
    )
    info("")
    info(
        "[dim]If you just deployed the key, GitHub Pages may still"
        " be building. Wait a minute and try again.[/dim]"
    )


# ---------------------------------------------------------------------------
# Phase 5: OAuth login
# ---------------------------------------------------------------------------


async def _oauth_login_step(
    formatter: OutputFormatter,
    app_ctx: AppContext,
    settings: AppSettings,
    client_id: str,
    client_secret: str,
) -> None:
    """Run the OAuth2 login flow."""
    info = formatter.rich.info

    from tescmd.auth.token_store import TokenStore
    from tescmd.models.auth import DEFAULT_SCOPES

    store = TokenStore(
        profile=app_ctx.profile,
        token_file=settings.token_file,
        config_dir=settings.config_dir,
    )

    if store.has_token:
        # Check whether the stored scopes cover what we need.
        # A readonly→full upgrade requires vehicle_cmds + vehicle_charging_cmds
        # that the original readonly token may not have.
        stored_scopes = set((store.metadata or {}).get("scopes", []))
        required_scopes = set(DEFAULT_SCOPES)
        missing = required_scopes - stored_scopes

        if not missing:
            info("Already logged in with required scopes. Skipping OAuth flow.")
            info("")
            return

        info("[bold]Phase 5: OAuth Login[/bold]")
        info("")
        info("[yellow]Your existing token is missing scopes needed for full control:[/yellow]")
        for scope in sorted(missing):
            info(f"  - {scope}")
        info("")
        info("Re-authenticating to request all required scopes...")
        info("")
    else:
        info("[bold]Phase 5: OAuth Login[/bold]")
        info("")

    from tescmd.models.auth import DEFAULT_PORT as _DEFAULT_PORT

    port = _DEFAULT_PORT
    redirect_uri = f"http://localhost:{port}/callback"

    info("Opening your browser to sign in to Tesla...")
    info(
        "When prompted, click [cyan]Select All[/cyan] and then"
        " [cyan]Allow[/cyan] to grant tescmd access."
    )
    info("[dim]If the browser doesn't open, visit the URL printed below.[/dim]")

    from tescmd.auth.oauth import login_flow

    region = app_ctx.region or settings.region

    await login_flow(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=DEFAULT_SCOPES,
        port=port,
        token_store=store,
        region=region,
    )

    info("[bold green]Login successful![/bold green]")
    info("")


# ---------------------------------------------------------------------------
# Phase 6: Next steps
# ---------------------------------------------------------------------------


def _print_next_steps(formatter: OutputFormatter, tier: str) -> None:
    """Print a summary of what the user can do next."""
    info = formatter.rich.info

    info("[bold cyan]Setup complete![/bold cyan]")
    info("")
    info("Try these commands:")
    info("  [cyan]tescmd vehicle list[/cyan]     — list your vehicles")
    info("  [cyan]tescmd vehicle data[/cyan]     — view detailed vehicle data")
    info("  [cyan]tescmd vehicle location[/cyan] — view vehicle location")
    info("")

    if tier == TIER_FULL:
        info("[bold]For vehicle commands:[/bold]")
        info("  If you haven't already, enroll your key on each vehicle:")
        info("  [cyan]tescmd key enroll[/cyan]")
        info("")
        info("  Once enrolled, try:")
        info("  [cyan]tescmd vehicle wake[/cyan]  — wake up your vehicle")
        info("")
        info("[bold]For real-time streaming data:[/bold]")
        info(
            "  Fleet Telemetry can replace REST polling with server-push,"
            " cutting API costs by up to 97%."
        )
        info(
            "  See: [cyan]https://developer.tesla.com/docs/fleet-api"
            "/getting-started/fleet-telemetry[/cyan]"
        )
        info("")
    else:
        info(
            "[dim]Upgrade to full control later by running [cyan]tescmd setup[/cyan] again.[/dim]"
        )
        info("")
