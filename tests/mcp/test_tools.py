"""Tests for MCP tool parameter mapping and JSON envelope validation."""

from __future__ import annotations

from tescmd.mcp.server import _READ_TOOLS, _WRITE_TOOLS, MCPServer


class TestToolParameterMapping:
    def test_all_read_tools_have_valid_args(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        for name in _READ_TOOLS:
            tool = server._tools[name]
            assert isinstance(tool.args, list)
            assert len(tool.args) >= 2, f"{name} should have at least group + command"
            assert tool.is_write is False

    def test_all_write_tools_have_valid_args(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        for name in _WRITE_TOOLS:
            tool = server._tools[name]
            assert isinstance(tool.args, list)
            assert len(tool.args) >= 2, f"{name} should have at least group + command"
            assert tool.is_write is True

    def test_no_duplicate_tool_names(self) -> None:
        all_names = list(_READ_TOOLS.keys()) + list(_WRITE_TOOLS.keys())
        assert len(all_names) == len(set(all_names)), "Duplicate tool names found"


class TestToolDescriptions:
    def test_all_tools_have_descriptions(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        for name, defn in server._tools.items():
            assert defn.description, f"Tool {name} has empty description"
            assert len(defn.description) > 5, f"Tool {name} has very short description"


class TestNavToolsRegistered:
    def test_nav_gps_registered(self) -> None:
        assert "nav_gps" in _WRITE_TOOLS
        args, _desc = _WRITE_TOOLS["nav_gps"]
        assert args == ["nav", "gps"]

    def test_nav_waypoints_registered(self) -> None:
        assert "nav_waypoints" in _WRITE_TOOLS
        args, _desc = _WRITE_TOOLS["nav_waypoints"]
        assert args == ["nav", "waypoints"]

    def test_nav_homelink_registered(self) -> None:
        assert "nav_homelink" in _WRITE_TOOLS
        args, _desc = _WRITE_TOOLS["nav_homelink"]
        assert args == ["nav", "homelink"]

    def test_nav_tools_are_write_tools(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        for name in ("nav_send", "nav_gps", "nav_supercharger", "nav_waypoints", "nav_homelink"):
            assert name in server._tools, f"{name} not found in server tools"
            assert server._tools[name].is_write is True, f"{name} should be a write tool"


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
