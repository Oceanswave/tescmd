"""GitHub Pages deployment helpers for Tesla Fleet API public keys.

All Git/GitHub operations go through ``_run_gh`` and ``_run_git`` helpers
so that tests can mock subprocess calls cleanly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

WELL_KNOWN_PATH = ".well-known/appspecific/com.tesla.3p.public-key.pem"

# Timeout and polling for GitHub Pages deployment
DEFAULT_DEPLOY_TIMEOUT = 180  # seconds
POLL_INTERVAL = 5  # seconds


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _run_gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a ``gh`` CLI command and return the result."""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _run_git(
    args: list[str],
    *,
    cwd: Path | str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a ``git`` command and return the result."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=check,
    )


# ---------------------------------------------------------------------------
# GitHub CLI queries
# ---------------------------------------------------------------------------


def is_gh_available() -> bool:
    """Return True if the ``gh`` CLI is installed on PATH."""
    return shutil.which("gh") is not None


def is_gh_authenticated() -> bool:
    """Return True if ``gh`` is authenticated with GitHub."""
    if not is_gh_available():
        return False
    result = _run_gh(["auth", "status"], check=False)
    return result.returncode == 0


def get_gh_username() -> str:
    """Return the authenticated GitHub username.

    Raises ``RuntimeError`` if ``gh`` is not authenticated.
    """
    result = _run_gh(["api", "user", "--jq", ".login"])
    username = result.stdout.strip()
    if not username:
        raise RuntimeError("Could not determine GitHub username from 'gh api user'.")
    return username


def repo_exists(repo_name: str) -> bool:
    """Return True if the given ``owner/repo`` exists on GitHub."""
    result = _run_gh(["repo", "view", repo_name], check=False)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Repository creation and key deployment
# ---------------------------------------------------------------------------


def create_pages_repo(username: str) -> str:
    """Create ``<username>.github.io`` if it doesn't exist.

    Returns the full repo name (``username/username.github.io``).
    """
    repo_name = f"{username}/{username}.github.io"

    if repo_exists(repo_name):
        return repo_name

    _run_gh(
        [
            "repo",
            "create",
            repo_name,
            "--public",
            "--description",
            "GitHub Pages site for Tesla Fleet API key hosting",
        ]
    )

    return repo_name


def deploy_public_key(public_key_pem: str, repo_name: str) -> None:
    """Clone *repo_name*, add the Tesla public key, and push.

    Handles:
    - Empty repos (no initial commit)
    - Existing ``_config.yml`` (merges ``include`` directive)
    - Already-deployed key (skips commit if no changes)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_dir = Path(tmpdir) / "repo"
        _clone_or_init(repo_name, clone_dir)

        # Ensure .well-known directory structure
        key_path = clone_dir / WELL_KNOWN_PATH
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(public_key_pem)

        # Ensure _config.yml includes .well-known
        _ensure_jekyll_config(clone_dir)

        # Ensure .nojekyll exists
        nojekyll = clone_dir / ".nojekyll"
        if not nojekyll.exists():
            nojekyll.touch()

        # Create minimal index.html if repo is empty
        index = clone_dir / "index.html"
        if not index.exists():
            index.write_text(
                "<!DOCTYPE html>\n"
                "<html><head><title>Tesla Fleet API</title></head>\n"
                "<body><p>Tesla Fleet API key host.</p></body></html>\n"
            )

        # Stage all changes
        _run_git(["add", "-A"], cwd=clone_dir)

        # Check if there are changes to commit
        status = _run_git(["status", "--porcelain"], cwd=clone_dir)
        if not status.stdout.strip():
            return  # Nothing to commit — key already deployed

        _run_git(
            ["commit", "-m", "Deploy Tesla Fleet API public key"],
            cwd=clone_dir,
        )
        _run_git(["push", "origin", "HEAD"], cwd=clone_dir)


def _clone_or_init(repo_name: str, clone_dir: Path) -> None:
    """Clone the repo, handling the empty-repo case."""
    result = _run_gh(
        ["repo", "clone", repo_name, str(clone_dir), "--", "--depth=1"],
        check=False,
    )

    if result.returncode == 0:
        return

    # Empty repo: gh clone fails — manually init + add remote
    clone_dir.mkdir(parents=True, exist_ok=True)
    _run_git(["init"], cwd=clone_dir)
    _run_git(
        ["remote", "add", "origin", f"https://github.com/{repo_name}.git"],
        cwd=clone_dir,
    )
    # Set default branch to main
    _run_git(["checkout", "-b", "main"], cwd=clone_dir)


def _ensure_jekyll_config(clone_dir: Path) -> None:
    """Ensure ``_config.yml`` includes ``.well-known`` in its ``include`` list."""
    config_path = clone_dir / "_config.yml"

    if config_path.exists():
        content = config_path.read_text()
        if ".well-known" in content:
            return  # Already configured
        # Append include directive
        content = content.rstrip("\n") + "\n\ninclude:\n  - .well-known\n"
        config_path.write_text(content)
    else:
        config_path.write_text('include:\n  - ".well-known"\n')


# ---------------------------------------------------------------------------
# Deployment validation
# ---------------------------------------------------------------------------


def get_key_url(domain: str) -> str:
    """Return the full URL where the public key should be served."""
    return f"https://{domain}/{WELL_KNOWN_PATH}"


def validate_key_url(domain: str) -> bool:
    """Return True if the public key is accessible at the expected URL."""
    url = get_key_url(domain)
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=10)
        return resp.status_code == 200 and "BEGIN PUBLIC KEY" in resp.text
    except httpx.HTTPError:
        return False


def wait_for_pages_deployment(
    domain: str,
    *,
    timeout: int = DEFAULT_DEPLOY_TIMEOUT,
) -> bool:
    """Poll the key URL until it responds successfully or *timeout* elapses.

    Returns True if the key became accessible, False on timeout.
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if validate_key_url(domain):
            return True
        time.sleep(POLL_INTERVAL)

    return False


def get_pages_domain(repo_name: str) -> str:
    """Infer the GitHub Pages domain from a repo name.

    For ``user/user.github.io`` → ``user.github.io``.
    For ``user/other-repo`` → ``user.github.io/other-repo`` (project page).

    The result is always lowercased because the Tesla Fleet API rejects
    domains with uppercase characters.
    """
    parts = repo_name.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid repo name: {repo_name!r}")

    owner, name = parts
    if name.lower() == f"{owner.lower()}.github.io":
        return name.lower()
    return f"{owner.lower()}.github.io/{name.lower()}"


def get_repo_info(repo_name: str) -> dict[str, str]:
    """Return basic repo metadata from the GitHub API."""
    result = _run_gh(["repo", "view", repo_name, "--json", "name,owner,url"])
    data: dict[str, str] = json.loads(result.stdout)
    return data
