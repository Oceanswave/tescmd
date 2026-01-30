"""CLI commands for EC key management (generate, deploy, validate, show)."""

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
