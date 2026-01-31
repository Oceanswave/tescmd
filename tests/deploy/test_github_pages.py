"""Tests for GitHub Pages deployment helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tescmd.deploy import github_pages as gh


def _ok(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Helper to create a successful CompletedProcess."""
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=stderr)


def _fail(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Helper to create a failed CompletedProcess."""
    return subprocess.CompletedProcess(args=[], returncode=1, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# gh availability and authentication
# ---------------------------------------------------------------------------


class TestIsGhAvailable:
    def test_available(self) -> None:
        with patch("tescmd.deploy.github_pages.shutil.which", return_value="/usr/bin/gh"):
            assert gh.is_gh_available() is True

    def test_not_available(self) -> None:
        with patch("tescmd.deploy.github_pages.shutil.which", return_value=None):
            assert gh.is_gh_available() is False


class TestIsGhAuthenticated:
    def test_authenticated(self) -> None:
        with (
            patch("tescmd.deploy.github_pages.shutil.which", return_value="/usr/bin/gh"),
            patch("tescmd.deploy.github_pages._run_gh", return_value=_ok()),
        ):
            assert gh.is_gh_authenticated() is True

    def test_not_authenticated(self) -> None:
        with (
            patch("tescmd.deploy.github_pages.shutil.which", return_value="/usr/bin/gh"),
            patch("tescmd.deploy.github_pages._run_gh", return_value=_fail()),
        ):
            assert gh.is_gh_authenticated() is False

    def test_gh_not_installed(self) -> None:
        with patch("tescmd.deploy.github_pages.shutil.which", return_value=None):
            assert gh.is_gh_authenticated() is False


class TestGetGhUsername:
    def test_returns_username(self) -> None:
        with patch("tescmd.deploy.github_pages._run_gh", return_value=_ok("octocat\n")):
            assert gh.get_gh_username() == "octocat"

    def test_raises_on_empty(self) -> None:
        with (
            patch("tescmd.deploy.github_pages._run_gh", return_value=_ok("")),
            pytest.raises(RuntimeError, match="Could not determine"),
        ):
            gh.get_gh_username()


class TestRepoExists:
    def test_exists(self) -> None:
        with patch("tescmd.deploy.github_pages._run_gh", return_value=_ok()):
            assert gh.repo_exists("octocat/octocat.github.io") is True

    def test_not_exists(self) -> None:
        with patch("tescmd.deploy.github_pages._run_gh", return_value=_fail()):
            assert gh.repo_exists("octocat/nonexistent") is False


# ---------------------------------------------------------------------------
# Repository creation
# ---------------------------------------------------------------------------


class TestCreatePagesRepo:
    def test_creates_new_repo(self) -> None:
        calls: list[list[str]] = []

        def mock_gh(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[0] == "repo" and args[1] == "view":
                return _fail()
            return _ok()

        with patch("tescmd.deploy.github_pages._run_gh", side_effect=mock_gh):
            name = gh.create_pages_repo("octocat")

        assert name == "octocat/octocat.github.io"
        assert any("create" in c for c in calls)

    def test_skips_if_exists(self) -> None:
        with patch("tescmd.deploy.github_pages._run_gh", return_value=_ok()):
            name = gh.create_pages_repo("octocat")

        assert name == "octocat/octocat.github.io"


# ---------------------------------------------------------------------------
# Key deployment
# ---------------------------------------------------------------------------


class TestDeployPublicKey:
    def test_deploys_key(self, tmp_path: Path) -> None:
        clone_dir: Path | None = None

        def mock_gh(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            nonlocal clone_dir
            if args[0] == "repo" and args[1] == "clone":
                # Simulate clone by creating the directory
                clone_dir = Path(args[3])
                clone_dir.mkdir(parents=True, exist_ok=True)
                return _ok()
            return _ok()

        git_calls: list[list[str]] = []

        def mock_git(
            args: list[str], *, cwd: Any = None, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            git_calls.append(args)
            if args[0] == "status":
                return _ok("M .well-known/appspecific/com.tesla.3p.public-key.pem")
            return _ok()

        with (
            patch("tescmd.deploy.github_pages._run_gh", side_effect=mock_gh),
            patch("tescmd.deploy.github_pages._run_git", side_effect=mock_git),
        ):
            gh.deploy_public_key("-----BEGIN PUBLIC KEY-----\ntest\n", "octocat/octocat.github.io")

        # Should have committed and pushed
        assert any("commit" in c for c in git_calls)
        assert any("push" in c for c in git_calls)

    def test_skips_commit_when_no_changes(self) -> None:
        def mock_gh(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            if args[0] == "repo" and args[1] == "clone":
                clone_dir = Path(args[3])
                clone_dir.mkdir(parents=True, exist_ok=True)
                return _ok()
            return _ok()

        git_calls: list[list[str]] = []

        def mock_git(
            args: list[str], *, cwd: Any = None, **kwargs: Any
        ) -> subprocess.CompletedProcess[str]:
            git_calls.append(args)
            if args[0] == "status":
                return _ok("")  # No changes
            return _ok()

        with (
            patch("tescmd.deploy.github_pages._run_gh", side_effect=mock_gh),
            patch("tescmd.deploy.github_pages._run_git", side_effect=mock_git),
        ):
            gh.deploy_public_key("-----BEGIN PUBLIC KEY-----\ntest\n", "user/user.github.io")

        assert not any("commit" in c for c in git_calls)


# ---------------------------------------------------------------------------
# Jekyll config
# ---------------------------------------------------------------------------


class TestEnsureJekyllConfig:
    def test_creates_new_config(self, tmp_path: Path) -> None:
        gh._ensure_jekyll_config(tmp_path)
        config = (tmp_path / "_config.yml").read_text()
        assert ".well-known" in config

    def test_merges_existing_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "_config.yml"
        config_path.write_text("title: My Site\n")
        gh._ensure_jekyll_config(tmp_path)
        content = config_path.read_text()
        assert "title: My Site" in content
        assert ".well-known" in content

    def test_skips_if_already_configured(self, tmp_path: Path) -> None:
        config_path = tmp_path / "_config.yml"
        original = 'include:\n  - ".well-known"\n'
        config_path.write_text(original)
        gh._ensure_jekyll_config(tmp_path)
        assert config_path.read_text() == original


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


class TestGetKeyUrl:
    def test_returns_url(self) -> None:
        url = gh.get_key_url("octocat.github.io")
        assert url == (
            "https://octocat.github.io/.well-known/appspecific/com.tesla.3p.public-key.pem"
        )


class TestGetPagesDomain:
    def test_user_page(self) -> None:
        assert gh.get_pages_domain("octocat/octocat.github.io") == "octocat.github.io"

    def test_project_page(self) -> None:
        assert gh.get_pages_domain("octocat/my-project") == "octocat.github.io/my-project"

    def test_mixed_case_lowercased(self) -> None:
        assert gh.get_pages_domain("Testuser/Testuser.github.io") == "testuser.github.io"

    def test_mixed_case_project_page(self) -> None:
        assert gh.get_pages_domain("Testuser/My-Project") == "testuser.github.io/my-project"

    def test_invalid_repo_name(self) -> None:
        with pytest.raises(ValueError, match="Invalid repo name"):
            gh.get_pages_domain("no-slash")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateKeyUrl:
    def test_valid(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----"

        with patch("tescmd.deploy.github_pages.httpx.get", return_value=mock_resp):
            assert gh.validate_key_url("octocat.github.io") is True

    def test_not_found(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        with patch("tescmd.deploy.github_pages.httpx.get", return_value=mock_resp):
            assert gh.validate_key_url("octocat.github.io") is False

    def test_wrong_content(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>Not a key</html>"

        with patch("tescmd.deploy.github_pages.httpx.get", return_value=mock_resp):
            assert gh.validate_key_url("octocat.github.io") is False

    def test_connection_error(self) -> None:
        import httpx as httpx_mod

        with patch(
            "tescmd.deploy.github_pages.httpx.get",
            side_effect=httpx_mod.ConnectError(
                "Connection refused",
                request=httpx_mod.Request("GET", "https://nonexistent.example.com"),
            ),
        ):
            assert gh.validate_key_url("nonexistent.example.com") is False


class TestWaitForPagesDeployment:
    def test_immediate_success(self) -> None:
        with patch("tescmd.deploy.github_pages.validate_key_url", return_value=True):
            assert gh.wait_for_pages_deployment("octocat.github.io", timeout=10) is True

    def test_eventual_success(self) -> None:
        call_count = 0

        def mock_validate(domain: str) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 3

        with (
            patch("tescmd.deploy.github_pages.validate_key_url", side_effect=mock_validate),
            patch("tescmd.deploy.github_pages.time.sleep"),
        ):
            assert gh.wait_for_pages_deployment("octocat.github.io", timeout=60) is True

    def test_timeout(self) -> None:
        with (
            patch("tescmd.deploy.github_pages.validate_key_url", return_value=False),
            patch(
                "tescmd.deploy.github_pages.time.monotonic",
                side_effect=[0.0, 200.0],  # Already past deadline on first poll check
            ),
        ):
            assert gh.wait_for_pages_deployment("bad.example.com", timeout=10) is False
