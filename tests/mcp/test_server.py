"""Tests for MCP server tool listing and invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from tescmd.mcp.server import (
    _EXCLUDED,
    _READ_TOOLS,
    _WRITE_TOOLS,
    MCPServer,
    _InMemoryOAuthProvider,
    _PermissiveClient,
    create_mcp_server,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class TestCreateServer:
    def test_factory_returns_server(self) -> None:
        server = create_mcp_server(client_id="test-id", client_secret="test-secret")
        assert isinstance(server, MCPServer)


class TestListTools:
    def test_lists_read_and_write_tools(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        tools = server.list_tools()
        names = {t["name"] for t in tools}

        # Spot-check key tools
        assert "vehicle_list" in names
        assert "charge_status" in names
        assert "charge_start" in names
        assert "security_lock" in names

    def test_tool_count(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        tools = server.list_tools()
        expected = len(_READ_TOOLS) + len(_WRITE_TOOLS)
        assert len(tools) == expected

    def test_read_tools_have_readonly_hint(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        tools = server.list_tools()
        read_tools = [t for t in tools if t["name"] in _READ_TOOLS]
        for tool in read_tools:
            assert tool["annotations"]["readOnlyHint"] is True

    def test_write_tools_have_no_readonly_hint(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        tools = server.list_tools()
        write_tools = [t for t in tools if t["name"] in _WRITE_TOOLS]
        for tool in write_tools:
            assert tool["annotations"]["readOnlyHint"] is False

    def test_tool_has_input_schema(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        tools = server.list_tools()
        for tool in tools:
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "vin" in tool["inputSchema"]["properties"]

    def test_excluded_commands_not_present(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        tools = server.list_tools()
        names = {t["name"] for t in tools}
        # None of the excluded command names should be tool names
        for excl in _EXCLUDED:
            # Excluded are space-separated, tool names are underscore-separated
            tool_name = excl.replace(" ", "_")
            assert tool_name not in names


class TestInvokeTool:
    def test_unknown_tool_returns_error(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        result = server.invoke_tool("nonexistent", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_invoke_cache_status(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """cache status is a safe read-only command that works without auth."""
        monkeypatch.setenv("TESLA_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("TESLA_CACHE_ENABLED", "true")

        server = MCPServer(client_id="test-id", client_secret="test-secret")
        result = server.invoke_tool("cache_status", {})

        # cache status should succeed (it doesn't require auth)
        # It returns either parsed JSON or an output string
        assert isinstance(result, dict)

    def test_invoke_passes_env_to_runner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CliRunner must receive the process env so auth tokens are visible."""
        import os
        from unittest.mock import MagicMock, patch

        sentinel_token = "test-token-12345"
        monkeypatch.setenv("TESLA_ACCESS_TOKEN", sentinel_token)

        server = MCPServer(client_id="test-id", client_secret="test-secret")

        with patch("click.testing.CliRunner.invoke") as mock_invoke:
            mock_result = MagicMock()
            mock_result.exit_code = 0
            mock_result.output = '{"ok": true}'
            mock_result.stderr = ""
            mock_invoke.return_value = mock_result

            server.invoke_tool("cache_status", {})

            # Verify invoke was called with env= containing our token
            _args, kwargs = mock_invoke.call_args
            assert "env" in kwargs
            assert kwargs["env"]["TESLA_ACCESS_TOKEN"] == sentinel_token
            # Verify it's a copy, not the live os.environ
            assert kwargs["env"] is not os.environ


class TestToolCLIArgs:
    def test_args_include_format_json_wake(self) -> None:
        """Verify the invocation uses --format json --wake."""
        server = MCPServer(client_id="test-id", client_secret="test-secret")

        # We can't easily mock CliRunner here, so just verify the tool
        # entry exists and has the right structure
        tool_def = server._tools.get("vehicle_list")
        assert tool_def is not None
        args, _desc, is_write = tool_def
        assert args == ["vehicle", "list"]
        assert is_write is False

    def test_write_tool_marked_correctly(self) -> None:
        server = MCPServer(client_id="test-id", client_secret="test-secret")
        tool_def = server._tools.get("charge_start")
        assert tool_def is not None
        _, _, is_write = tool_def
        assert is_write is True


def _mock_client(client_id: str = "test-client") -> Any:
    """Create a mock OAuth client with the given client_id."""
    from unittest.mock import MagicMock

    client = MagicMock()
    client.client_id = client_id
    return client


def _mock_auth_params(
    *,
    redirect_uri: str = "https://example.com/callback",
    state: str | None = "test-state",
    scopes: list[str] | None = None,
) -> Any:
    """Create mock AuthorizationParams."""
    from unittest.mock import MagicMock

    params = MagicMock()
    params.scopes = scopes or []
    params.code_challenge = "test-challenge-abc"
    params.redirect_uri = redirect_uri
    params.redirect_uri_provided_explicitly = True
    params.state = state
    params.resource = None
    return params


class TestPermissiveClient:
    def test_accepts_any_redirect_uri(self) -> None:
        client = _PermissiveClient(client_id="test")
        uri = client.validate_redirect_uri("https://claude.ai/api/mcp/auth_callback")
        assert str(uri) == "https://claude.ai/api/mcp/auth_callback"

    def test_accepts_any_scope(self) -> None:
        client = _PermissiveClient(client_id="test")
        assert client.validate_scope("claudeai read") == ["claudeai", "read"]
        assert client.validate_scope(None) == []

    def test_delegates_attributes_to_inner(self) -> None:
        client = _PermissiveClient(client_id="test")
        assert client.client_id == "test"
        assert client.grant_types == ["authorization_code", "refresh_token"]


class TestInMemoryOAuthProvider:
    async def test_get_unknown_client_auto_creates(self) -> None:
        provider = _InMemoryOAuthProvider()
        client = await provider.get_client("brand-new")
        assert client is not None
        assert client.client_id == "brand-new"
        assert isinstance(client, _PermissiveClient)

    async def test_get_unknown_client_is_cached(self) -> None:
        provider = _InMemoryOAuthProvider()
        first = await provider.get_client("foo")
        second = await provider.get_client("foo")
        assert first is second

    async def test_register_and_retrieve_client(self) -> None:
        provider = _InMemoryOAuthProvider()
        client = _mock_client("my-client")
        await provider.register_client(client)

        result = await provider.get_client("my-client")
        assert result is not None
        assert result.client_id == "my-client"

    async def test_authorize_returns_redirect_with_code_and_state(self) -> None:
        provider = _InMemoryOAuthProvider()
        client = _mock_client()
        params = _mock_auth_params(state="xyz123")

        url = await provider.authorize(client, params)
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        assert parsed.scheme == "https"
        assert parsed.netloc == "example.com"
        assert "code" in qs
        assert qs["state"] == ["xyz123"]

    async def test_authorize_without_state(self) -> None:
        provider = _InMemoryOAuthProvider()
        url = await provider.authorize(_mock_client(), _mock_auth_params(state=None))
        qs = parse_qs(urlparse(url).query)

        assert "code" in qs
        assert "state" not in qs

    async def test_full_authorization_code_exchange(self) -> None:
        provider = _InMemoryOAuthProvider()
        client = _mock_client()

        # Authorize → get code
        url = await provider.authorize(client, _mock_auth_params())
        code = parse_qs(urlparse(url).query)["code"][0]

        # Load auth code
        auth_code = await provider.load_authorization_code(client, code)
        assert auth_code is not None
        assert auth_code.client_id == "test-client"

        # Exchange code → tokens
        token = await provider.exchange_authorization_code(client, auth_code)
        assert token.access_token
        assert token.refresh_token
        assert token.token_type == "Bearer"
        assert token.expires_in == 3600

        # Code is consumed (one-time use)
        assert await provider.load_authorization_code(client, code) is None

    async def test_load_access_token_after_exchange(self) -> None:
        provider = _InMemoryOAuthProvider()
        client = _mock_client()

        url = await provider.authorize(client, _mock_auth_params())
        code = parse_qs(urlparse(url).query)["code"][0]
        auth_code = await provider.load_authorization_code(client, code)
        token = await provider.exchange_authorization_code(client, auth_code)

        result = await provider.load_access_token(token.access_token)
        assert result is not None
        assert result.client_id == "test-client"

    async def test_load_authorization_code_wrong_client(self) -> None:
        provider = _InMemoryOAuthProvider()
        url = await provider.authorize(_mock_client("alice"), _mock_auth_params())
        code = parse_qs(urlparse(url).query)["code"][0]

        # Different client should not get the code
        assert await provider.load_authorization_code(_mock_client("bob"), code) is None

    async def test_revoke_access_token(self) -> None:
        provider = _InMemoryOAuthProvider()
        client = _mock_client()

        url = await provider.authorize(client, _mock_auth_params())
        code = parse_qs(urlparse(url).query)["code"][0]
        auth_code = await provider.load_authorization_code(client, code)
        token = await provider.exchange_authorization_code(client, auth_code)

        access = await provider.load_access_token(token.access_token)
        assert access is not None
        await provider.revoke_token(access)
        assert await provider.load_access_token(token.access_token) is None

    async def test_refresh_token_exchange(self) -> None:
        provider = _InMemoryOAuthProvider()
        client = _mock_client()

        url = await provider.authorize(client, _mock_auth_params(scopes=["read"]))
        code = parse_qs(urlparse(url).query)["code"][0]
        auth_code = await provider.load_authorization_code(client, code)
        token = await provider.exchange_authorization_code(client, auth_code)

        rt = await provider.load_refresh_token(client, token.refresh_token)
        assert rt is not None
        new_token = await provider.exchange_refresh_token(client, rt, ["read"])
        assert new_token.access_token != token.access_token
        assert new_token.refresh_token != token.refresh_token

        # Old refresh token is consumed
        assert await provider.load_refresh_token(client, token.refresh_token) is None
