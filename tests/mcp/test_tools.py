"""Tests for MCP tool parameter mapping and JSON envelope validation."""

from __future__ import annotations

from tescmd.mcp.server import _READ_TOOLS, _WRITE_TOOLS, MCPServer


class TestToolParameterMapping:
    def test_all_read_tools_have_valid_args(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        for name in _READ_TOOLS:
            tool = server._tools[name]
            args, _desc, is_write = tool
            assert isinstance(args, list)
            assert len(args) >= 2, f"{name} should have at least group + command"
            assert is_write is False

    def test_all_write_tools_have_valid_args(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        for name in _WRITE_TOOLS:
            tool = server._tools[name]
            args, _desc, is_write = tool
            assert isinstance(args, list)
            assert len(args) >= 2, f"{name} should have at least group + command"
            assert is_write is True

    def test_no_duplicate_tool_names(self) -> None:
        all_names = list(_READ_TOOLS.keys()) + list(_WRITE_TOOLS.keys())
        assert len(all_names) == len(set(all_names)), "Duplicate tool names found"


class TestToolDescriptions:
    def test_all_tools_have_descriptions(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        for name, (_args, desc, _is_write) in server._tools.items():
            assert desc, f"Tool {name} has empty description"
            assert len(desc) > 5, f"Tool {name} has very short description"


class TestHelpOutput:
    def test_openclaw_bridge_help(self) -> None:
        from click.testing import CliRunner

        from tescmd.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["openclaw", "bridge", "--help"])
        assert result.exit_code == 0
        assert "OpenClaw Gateway" in result.output
        assert "--gateway" in result.output
        assert "--dry-run" in result.output

    def test_mcp_serve_help(self) -> None:
        from click.testing import CliRunner

        from tescmd.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["mcp", "serve", "--help"])
        assert result.exit_code == 0
        assert "MCP" in result.output
        assert "--transport" in result.output
        assert "--tailscale" in result.output
        assert "--client-id" in result.output
        assert "--client-secret" in result.output
