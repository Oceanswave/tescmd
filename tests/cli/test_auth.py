"""Tests for auth CLI helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tescmd.cli.auth import _prompt_for_domain


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
