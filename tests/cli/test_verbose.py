"""Tests for --verbose flag wiring — both root-level and subcommand-level."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    import pytest


class TestVerboseRootLevel:
    """--verbose before the subcommand configures logging."""

    def test_verbose_enables_debug_logging(
        self, cli_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Reset logging so basicConfig takes effect
        root = logging.getLogger()
        original_level = root.level
        original_handlers = root.handlers[:]
        try:
            root.handlers.clear()
            root.setLevel(logging.WARNING)

            runner = CliRunner()
            result = runner.invoke(cli, ["--verbose", "vehicle", "list"])
            # We don't care about the result — just that logging was configured
            assert result.exit_code in (0, 1)  # may fail due to mock, that's OK

            assert root.level == logging.DEBUG
        finally:
            root.setLevel(original_level)
            root.handlers[:] = original_handlers

    def test_no_verbose_leaves_logging_alone(self, cli_env: dict[str, str]) -> None:
        root = logging.getLogger()
        original_level = root.level
        original_handlers = root.handlers[:]
        try:
            root.handlers.clear()
            root.setLevel(logging.WARNING)

            runner = CliRunner()
            runner.invoke(cli, ["vehicle", "list"])

            # Without --verbose, root logger should stay at WARNING
            assert root.level == logging.WARNING
        finally:
            root.setLevel(original_level)
            root.handlers[:] = original_handlers


class TestVerboseSubcommandLevel:
    """--verbose after the subcommand also configures logging."""

    def test_verbose_after_subcommand(
        self, cli_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = logging.getLogger()
        original_level = root.level
        original_handlers = root.handlers[:]
        try:
            root.handlers.clear()
            root.setLevel(logging.WARNING)

            runner = CliRunner()
            result = runner.invoke(cli, ["vehicle", "list", "--verbose"])
            assert result.exit_code in (0, 1)

            assert root.level == logging.DEBUG
        finally:
            root.setLevel(original_level)
            root.handlers[:] = original_handlers
