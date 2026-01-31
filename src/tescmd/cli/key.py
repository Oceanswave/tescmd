"""CLI commands for EC key management (generate, deploy, validate, show, enroll)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from tescmd._internal.async_utils import run_async
from tescmd.cli._options import global_options
from tescmd.crypto.keys import (
    generate_ec_key_pair,
    get_key_fingerprint,
    get_public_key_path,
    has_key_pair,
    load_public_key_pem,
)
from tescmd.deploy.github_pages import (
    get_key_url,
    validate_key_url,
    wait_for_pages_deployment,
)
from tescmd.models.config import AppSettings

if TYPE_CHECKING:
    from tescmd.cli.main import AppContext


# ---------------------------------------------------------------------------
# Command group
# ---------------------------------------------------------------------------

key_group = click.Group("key", help="EC key management")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@key_group.command("generate")
@click.option("--force", is_flag=True, help="Overwrite existing keys")
@global_options
def generate_cmd(app_ctx: AppContext, force: bool) -> None:
    """Generate an EC P-256 key pair for Tesla Fleet API command signing."""
    run_async(_cmd_generate(app_ctx, force))


async def _cmd_generate(app_ctx: AppContext, force: bool) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()
    key_dir = Path(settings.config_dir).expanduser() / "keys"

    if has_key_pair(key_dir) and not force:
        if formatter.format == "json":
            formatter.output(
                {
                    "status": "exists",
                    "path": str(key_dir),
                    "fingerprint": get_key_fingerprint(key_dir),
                },
                command="key.generate",
            )
        else:
            formatter.rich.info(
                "[yellow]Key pair already exists.[/yellow] Use --force to overwrite."
            )
            formatter.rich.info(f"  Path: {key_dir}")
            formatter.rich.info(f"  Fingerprint: {get_key_fingerprint(key_dir)}")
        return

    priv_path, pub_path = generate_ec_key_pair(key_dir, overwrite=force)

    if formatter.format == "json":
        formatter.output(
            {
                "status": "generated",
                "private_key": str(priv_path),
                "public_key": str(pub_path),
                "fingerprint": get_key_fingerprint(key_dir),
            },
            command="key.generate",
        )
    else:
        formatter.rich.info("[green]Key pair generated.[/green]")
        formatter.rich.info(f"  Private key: {priv_path}")
        formatter.rich.info(f"  Public key:  {pub_path}")
        formatter.rich.info(f"  Fingerprint: {get_key_fingerprint(key_dir)}")


@key_group.command("deploy")
@click.option(
    "--repo",
    default=None,
    help="GitHub repo (e.g. user/user.github.io). Auto-detected if omitted.",
)
@global_options
def deploy_cmd(app_ctx: AppContext, repo: str | None) -> None:
    """Deploy the public key to GitHub Pages."""
    run_async(_cmd_deploy(app_ctx, repo))


async def _cmd_deploy(app_ctx: AppContext, repo: str | None) -> None:
    from tescmd.deploy.github_pages import (
        create_pages_repo,
        deploy_public_key,
        get_gh_username,
        get_pages_domain,
        is_gh_authenticated,
        is_gh_available,
    )

    formatter = app_ctx.formatter
    settings = AppSettings()
    key_dir = Path(settings.config_dir).expanduser() / "keys"

    # Ensure keys exist
    if not has_key_pair(key_dir):
        if formatter.format == "json":
            formatter.output_error(
                code="no_keys",
                message="No key pair found. Run 'tescmd key generate' first.",
                command="key.deploy",
            )
        else:
            formatter.rich.error("No key pair found. Run [cyan]tescmd key generate[/cyan] first.")
        return

    # Check gh CLI
    if not is_gh_available():
        if formatter.format == "json":
            formatter.output_error(
                code="gh_not_found",
                message="GitHub CLI (gh) is not installed. Install from https://cli.github.com",
                command="key.deploy",
            )
        else:
            formatter.rich.error(
                "GitHub CLI ([cyan]gh[/cyan]) is not installed."
                " Install from [link=https://cli.github.com]cli.github.com[/link]"
            )
        return

    if not is_gh_authenticated():
        if formatter.format == "json":
            formatter.output_error(
                code="gh_not_authenticated",
                message="GitHub CLI is not authenticated. Run 'gh auth login' first.",
                command="key.deploy",
            )
        else:
            formatter.rich.error(
                "GitHub CLI is not authenticated. Run [cyan]gh auth login[/cyan] first."
            )
        return

    # Determine repo
    repo_name: str | None = repo or settings.github_repo
    if not repo_name:
        username = get_gh_username()
        repo_name = f"{username}/{username}.github.io"
        if formatter.format != "json":
            formatter.rich.info(f"Using repo: [cyan]{repo_name}[/cyan]")

    # Create repo if needed and deploy
    if formatter.format != "json":
        formatter.rich.info("Creating repo if needed...")
    create_pages_repo(repo_name.split("/")[0])

    if formatter.format != "json":
        formatter.rich.info("Deploying public key...")

    pem = load_public_key_pem(key_dir)
    deploy_public_key(pem, repo_name)

    domain = get_pages_domain(repo_name)

    if formatter.format != "json":
        formatter.rich.info("[green]Key deployed.[/green]")
        formatter.rich.info(f"  URL: {get_key_url(domain)}")
        formatter.rich.info("")
        formatter.rich.info("Waiting for GitHub Pages to publish (this may take a few minutes)...")

    deployed = wait_for_pages_deployment(domain)

    if formatter.format == "json":
        formatter.output(
            {
                "status": "deployed" if deployed else "pending",
                "repo": repo_name,
                "domain": domain,
                "url": get_key_url(domain),
                "accessible": deployed,
            },
            command="key.deploy",
        )
    elif deployed:
        formatter.rich.info("[green]Key is live and accessible.[/green]")
    else:
        formatter.rich.info(
            "[yellow]Key deployed but not yet accessible."
            " GitHub Pages may still be building.[/yellow]"
        )
        formatter.rich.info("  Run [cyan]tescmd key validate[/cyan] to check again later.")


@key_group.command("validate")
@global_options
def validate_cmd(app_ctx: AppContext) -> None:
    """Check that the public key is accessible at the expected URL."""
    run_async(_cmd_validate(app_ctx))


async def _cmd_validate(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()
    domain = settings.domain

    if not domain:
        if formatter.format == "json":
            formatter.output_error(
                code="no_domain",
                message=(
                    "TESLA_DOMAIN is not set. Set it in your .env file or run"
                    " 'tescmd setup' to configure."
                ),
                command="key.validate",
            )
        else:
            formatter.rich.error(
                "No domain configured. Run [cyan]tescmd setup[/cyan]"
                " or set TESLA_DOMAIN in your .env file."
            )
        return

    url = get_key_url(domain)
    accessible = validate_key_url(domain)

    if formatter.format == "json":
        formatter.output(
            {"url": url, "accessible": accessible, "domain": domain},
            command="key.validate",
        )
    elif accessible:
        formatter.rich.info(f"[green]Public key is accessible at:[/green] {url}")
    else:
        formatter.rich.info(f"[red]Public key NOT accessible at:[/red] {url}")
        formatter.rich.info("")
        formatter.rich.info("Possible causes:")
        formatter.rich.info("  - Key has not been deployed yet")
        formatter.rich.info("  - GitHub Pages is still building")
        formatter.rich.info("  - Domain is not configured correctly")
        formatter.rich.info("")
        formatter.rich.info("Run [cyan]tescmd key deploy[/cyan] to deploy your key.")


@key_group.command("show")
@global_options
def show_cmd(app_ctx: AppContext) -> None:
    """Display key path and fingerprint."""
    run_async(_cmd_show(app_ctx))


async def _cmd_show(app_ctx: AppContext) -> None:
    formatter = app_ctx.formatter
    settings = AppSettings()
    key_dir = Path(settings.config_dir).expanduser() / "keys"

    if not has_key_pair(key_dir):
        if formatter.format == "json":
            formatter.output(
                {"status": "not_found", "path": str(key_dir)},
                command="key.show",
            )
        else:
            formatter.rich.info(
                "No key pair found. Run [cyan]tescmd key generate[/cyan] to create one."
            )
        return

    pub_path = get_public_key_path(key_dir)
    fingerprint = get_key_fingerprint(key_dir)

    if formatter.format == "json":
        formatter.output(
            {
                "status": "found",
                "path": str(key_dir),
                "public_key": str(pub_path),
                "fingerprint": fingerprint,
            },
            command="key.show",
        )
    else:
        formatter.rich.info(f"Key directory: {key_dir}")
        formatter.rich.info(f"Public key:    {pub_path}")
        formatter.rich.info(f"Fingerprint:   {fingerprint}")

        domain = settings.domain
        if domain:
            formatter.rich.info(f"Expected URL:  {get_key_url(domain)}")


# ---------------------------------------------------------------------------
# Enroll command
# ---------------------------------------------------------------------------

# Tesla app portal URL for key enrollment.
# Initial key enrollment is NOT available via REST API or signed_command.
# Tesla's Go SDK explicitly blocks add_key_request for Fleet API connections
# (ErrRequiresBLE).  For Fleet API apps, enrollment happens through the
# Tesla app portal: the user opens https://tesla.com/_ak/<domain> on their
# phone, and the Tesla app handles the actual key pairing with the vehicle.
_TESLA_APP_KEY_URL = "https://tesla.com/_ak/{domain}"

# Tesla consent revocation URL.  Revoking consent removes the app's
# OAuth access and its virtual key from all vehicles on the account.
# There is no Fleet API endpoint to remove a virtual key — Tesla requires
# the owner to revoke access through their account or the vehicle itself.
_TESLA_CONSENT_REVOKE_URL = (
    "https://auth.tesla.com/user/revoke/consent"
    "?revoke_client_id={client_id}&back_url=https://tesla.com"
)


@key_group.command("enroll")
@click.option(
    "--open/--no-open",
    default=True,
    help="Open the enrollment URL in the default browser (default: open)",
)
@global_options
def enroll_cmd(
    app_ctx: AppContext,
    open: bool,
) -> None:
    """Enroll your EC key on a vehicle via the Tesla app.

    Opens the Tesla app enrollment page for your domain.  The vehicle
    owner approves the key in the Tesla app (Profile >
    Security & Privacy > Third-Party Apps).  Once approved, signed commands work
    automatically.
    """
    run_async(_cmd_enroll(app_ctx, open_browser=open))


async def _cmd_enroll(
    app_ctx: AppContext,
    *,
    open_browser: bool,
) -> None:
    import webbrowser

    formatter = app_ctx.formatter
    settings = AppSettings()
    key_dir = Path(settings.config_dir).expanduser() / "keys"

    # Step 1: Check key pair
    if not has_key_pair(key_dir):
        if formatter.format == "json":
            formatter.output_error(
                code="no_keys",
                message="No key pair found. Run 'tescmd key generate' first.",
                command="key.enroll",
            )
        else:
            formatter.rich.error("No key pair found. Run [cyan]tescmd key generate[/cyan] first.")
        raise SystemExit(1)

    fingerprint = get_key_fingerprint(key_dir)

    if formatter.format != "json":
        formatter.rich.info("[bold]Step 1: Checking key pair…[/bold]")
        formatter.rich.info(f"  [green]✓[/green] Key pair found (fingerprint: {fingerprint[:8]}…)")
        formatter.rich.info("")

    # Step 2: Check domain is configured
    domain = settings.domain
    if not domain:
        if formatter.format == "json":
            formatter.output_error(
                code="no_domain",
                message=(
                    "No domain configured. Run 'tescmd setup' or set TESLA_DOMAIN"
                    " in your .env file."
                ),
                command="key.enroll",
            )
        else:
            formatter.rich.error(
                "No domain configured. Run [cyan]tescmd setup[/cyan]"
                " or set TESLA_DOMAIN in your .env file."
            )
        raise SystemExit(1)

    if formatter.format != "json":
        formatter.rich.info("[bold]Step 2: Checking domain & public key…[/bold]")

    # Step 3: Verify public key is accessible
    key_accessible = validate_key_url(domain)
    key_url = get_key_url(domain)

    if not key_accessible:
        if formatter.format == "json":
            formatter.output_error(
                code="key_not_accessible",
                message=(
                    f"Public key not accessible at {key_url}. "
                    "Deploy with 'tescmd key deploy' first."
                ),
                command="key.enroll",
            )
        else:
            formatter.rich.error(f"Public key not accessible at [cyan]{key_url}[/cyan]")
            formatter.rich.info("  Deploy with [cyan]tescmd key deploy[/cyan] first.")
        raise SystemExit(1)

    if formatter.format != "json":
        formatter.rich.info(f"  [green]✓[/green] Domain: {domain}")
        formatter.rich.info(f"  [green]✓[/green] Public key accessible at {key_url}")
        formatter.rich.info("")

    # Step 4: Build enrollment URL and guide user
    enroll_url = _TESLA_APP_KEY_URL.format(domain=domain)

    if formatter.format == "json":
        formatter.output(
            {
                "status": "ready",
                "domain": domain,
                "fingerprint": fingerprint,
                "enroll_url": enroll_url,
                "key_url": key_url,
                "message": (
                    f"Open {enroll_url} on your phone."
                    " Tap 'Finish Setup', then approve 'Add Virtual Key' in the Tesla app."
                ),
            },
            command="key.enroll",
        )
        return

    formatter.rich.info("[bold]Step 3: Key enrollment[/bold]")
    formatter.rich.info("")
    formatter.rich.info("━" * 55)
    formatter.rich.info(
        "  [bold yellow]ACTION REQUIRED: Add virtual key in the Tesla app[/bold yellow]"
    )
    formatter.rich.info("")
    formatter.rich.info(f"  Enrollment URL: [link={enroll_url}]{enroll_url}[/link]")
    formatter.rich.info("")
    formatter.rich.info("  1. Open the URL above [bold]on your phone[/bold]")
    formatter.rich.info("  2. Tap [bold]Finish Setup[/bold] on the web page")
    formatter.rich.info("  3. The Tesla app will show an [bold]Add Virtual Key[/bold] prompt")
    formatter.rich.info("  4. Approve it")
    formatter.rich.info("")
    formatter.rich.info("  [dim]If the prompt doesn't appear, force-quit the Tesla app,[/dim]")
    formatter.rich.info("  [dim]go back to your browser, and tap Finish Setup again.[/dim]")
    formatter.rich.info("━" * 55)
    formatter.rich.info("")

    if open_browser:
        formatter.rich.info("Opening enrollment URL in browser…")
        webbrowser.open(enroll_url)
        formatter.rich.info("")

    formatter.rich.info("After approving in the Tesla app, try a command:")
    formatter.rich.info("  [cyan]tescmd security lock --wake[/cyan]")
    formatter.rich.info("  [cyan]tescmd charge status --wake[/cyan]")
    formatter.rich.info("")
    formatter.rich.info(
        "[dim]Tip: This URL must be opened on your phone, not a desktop browser.[/dim]"
    )


# ---------------------------------------------------------------------------
# Unenroll command
# ---------------------------------------------------------------------------


@key_group.command("unenroll")
@click.option(
    "--open/--no-open",
    default=True,
    help="Open the revocation URL in the default browser (default: open)",
)
@global_options
def unenroll_cmd(
    app_ctx: AppContext,
    open: bool,
) -> None:
    """Remove your virtual key and revoke app access.

    Shows instructions for removing the tescmd virtual key from your
    vehicle(s) and optionally opens the Tesla consent revocation page
    to revoke OAuth access entirely.
    """
    run_async(_cmd_unenroll(app_ctx, open_browser=open))


async def _cmd_unenroll(
    app_ctx: AppContext,
    *,
    open_browser: bool,
) -> None:
    import webbrowser

    formatter = app_ctx.formatter
    settings = AppSettings()
    client_id = settings.client_id

    # Build revocation URL if client_id is available
    revoke_url: str | None = None
    if client_id:
        revoke_url = _TESLA_CONSENT_REVOKE_URL.format(client_id=client_id)

    if formatter.format == "json":
        data: dict[str, object] = {
            "status": "instructions",
            "revoke_url": revoke_url,
            "methods": [
                {
                    "name": "vehicle_touchscreen",
                    "steps": "Controls > Locks > tap trash icon on key > scan key card",
                    "speed": "immediate",
                },
                {
                    "name": "tesla_app",
                    "steps": "Profile > Security & Privacy > Third-Party Apps > Remove",
                    "speed": "up to 2 hours",
                },
                {
                    "name": "tesla_account_web",
                    "steps": "accounts.tesla.com > Security > Third Party Apps > Manage",
                    "speed": "up to 2 hours",
                },
            ],
            "message": (
                "Remove the virtual key via the vehicle touchscreen, Tesla app, "
                "or accounts.tesla.com. "
                + (
                    f"Revoke OAuth access at {revoke_url}"
                    if revoke_url
                    else "Set TESLA_CLIENT_ID to generate a consent revocation URL."
                )
            ),
        }
        formatter.output(data, command="key.unenroll")
        return

    formatter.rich.info("[bold]How to remove the tescmd virtual key[/bold]")
    formatter.rich.info("")
    formatter.rich.info("━" * 55)
    formatter.rich.info("")

    # Method 1: Vehicle touchscreen (immediate)
    formatter.rich.info("  [bold]Option 1: Vehicle touchscreen[/bold] [green](immediate)[/green]")
    formatter.rich.info("  1. On the vehicle touchscreen, tap [bold]Controls > Locks[/bold]")
    formatter.rich.info("  2. Find the tescmd key in the key list")
    formatter.rich.info("  3. Tap the [bold]trash icon[/bold] next to it")
    formatter.rich.info("  4. Scan your [bold]key card[/bold] on the card reader to confirm")
    formatter.rich.info("")

    # Method 2: Tesla app
    formatter.rich.info(
        "  [bold]Option 2: Tesla app[/bold] [yellow](may take up to 2 hours)[/yellow]"
    )
    formatter.rich.info("  1. Open the Tesla app > [bold]Profile > Security & Privacy[/bold]")
    formatter.rich.info("  2. Tap [bold]Third-Party Apps[/bold]")
    formatter.rich.info("  3. Find tescmd and tap [bold]Remove[/bold]")
    formatter.rich.info("")

    # Method 3: Tesla account website
    formatter.rich.info(
        "  [bold]Option 3: Tesla account website[/bold] [yellow](may take up to 2 hours)[/yellow]"
    )
    formatter.rich.info(
        "  1. Sign in at [link=https://accounts.tesla.com]accounts.tesla.com[/link]"
    )
    formatter.rich.info("  2. Go to [bold]Security > Third Party Apps[/bold]")
    formatter.rich.info("  3. Find tescmd and tap [bold]Manage > Remove[/bold]")
    formatter.rich.info("")
    formatter.rich.info("━" * 55)
    formatter.rich.info("")

    # OAuth consent revocation
    if revoke_url:
        formatter.rich.info("[bold]Revoke OAuth access entirely[/bold]")
        formatter.rich.info("")
        formatter.rich.info("  To also revoke this app's OAuth access to your Tesla account:")
        formatter.rich.info(f"  [link={revoke_url}]{revoke_url}[/link]")
        formatter.rich.info("")

        if open_browser:
            formatter.rich.info("Opening revocation page in browser…")
            webbrowser.open(revoke_url)
            formatter.rich.info("")
    else:
        formatter.rich.info("[dim]Set TESLA_CLIENT_ID to generate a consent revocation URL.[/dim]")
        formatter.rich.info("")

    # Cleanup guidance
    formatter.rich.info("[bold]Local cleanup[/bold]")
    formatter.rich.info("")
    formatter.rich.info("  To also remove local credentials and keys:")
    formatter.rich.info("  [cyan]tescmd auth logout[/cyan]     — clear stored OAuth tokens")
    formatter.rich.info("  [cyan]tescmd cache clear[/cyan]     — clear cached API responses")
    formatter.rich.info(
        f"  [dim]Key files are stored in: {Path(settings.config_dir).expanduser() / 'keys'}[/dim]"
    )
