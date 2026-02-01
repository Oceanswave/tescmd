"""FastMCP server factory exposing tescmd commands as MCP tools.

Uses Click's CliRunner to invoke tescmd commands, guaranteeing behavioral
parity with the CLI (caching, wake, auth, error handling all work).

Each tool calls ``runner.invoke(cli, ["--format", "json", "--wake", *args])``
and returns the JSON output.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions — command name → (args_template, description, is_write)
# ---------------------------------------------------------------------------

_READ_TOOLS: dict[str, tuple[list[str], str]] = {
    "vehicle_list": (["vehicle", "list"], "List all vehicles on the account"),
    "vehicle_info": (["vehicle", "info"], "Get vehicle info summary"),
    "vehicle_data": (["vehicle", "data"], "Get full vehicle data"),
    "vehicle_location": (["vehicle", "location"], "Get vehicle location"),
    "vehicle_alerts": (["vehicle", "alerts"], "Get vehicle alerts"),
    "vehicle_nearby_chargers": (
        ["vehicle", "nearby-chargers"],
        "Find nearby Superchargers and destination chargers",
    ),
    "vehicle_release_notes": (["vehicle", "release-notes"], "Get software release notes"),
    "vehicle_service": (["vehicle", "service"], "Get service status"),
    "vehicle_drivers": (["vehicle", "drivers"], "List authorized drivers"),
    "vehicle_specs": (["vehicle", "specs"], "Get vehicle specifications"),
    "vehicle_warranty": (["vehicle", "warranty"], "Get warranty information"),
    "vehicle_fleet_status": (["vehicle", "fleet-status"], "Get fleet telemetry status"),
    "vehicle_subscriptions": (["vehicle", "subscriptions"], "List subscriptions"),
    "charge_status": (["charge", "status"], "Get charge status"),
    "climate_status": (["climate", "status"], "Get climate status"),
    "security_status": (["security", "status"], "Get security/lock status"),
    "software_status": (["software", "status"], "Get software update status"),
    "energy_list": (["energy", "list"], "List energy products (Powerwall)"),
    "energy_status": (["energy", "status"], "Get energy site status"),
    "energy_live": (["energy", "live"], "Get live power flow data"),
    "energy_history": (["energy", "history"], "Get energy history"),
    "billing_history": (["billing", "history"], "Get Supercharger billing history"),
    "billing_sessions": (["billing", "sessions"], "Get Supercharger charging sessions"),
    "user_me": (["user", "me"], "Get account info"),
    "user_region": (["user", "region"], "Get account region"),
    "user_orders": (["user", "orders"], "Get vehicle orders"),
    "user_features": (["user", "features"], "Get feature flags"),
    "cache_status": (["cache", "status"], "Get cache status"),
    "auth_status": (["auth", "status"], "Get auth/token status"),
}

_WRITE_TOOLS: dict[str, tuple[list[str], str]] = {
    "charge_start": (["charge", "start"], "Start charging"),
    "charge_stop": (["charge", "stop"], "Stop charging"),
    "charge_limit": (["charge", "limit"], "Set charge limit (percentage)"),
    "charge_limit_max": (["charge", "limit-max"], "Set charge limit to maximum"),
    "charge_limit_std": (["charge", "limit-std"], "Set charge limit to standard"),
    "charge_amps": (["charge", "amps"], "Set charge amperage"),
    "charge_port_open": (["charge", "port-open"], "Open charge port"),
    "charge_port_close": (["charge", "port-close"], "Close charge port"),
    "climate_on": (["climate", "on"], "Turn on climate control"),
    "climate_off": (["climate", "off"], "Turn off climate control"),
    "climate_set": (["climate", "set"], "Set climate temperature"),
    "climate_precondition": (["climate", "precondition"], "Precondition cabin"),
    "climate_seat": (["climate", "seat"], "Set seat heater level"),
    "climate_wheel_heater": (["climate", "wheel-heater"], "Toggle steering wheel heater"),
    "climate_bioweapon": (["climate", "bioweapon"], "Toggle bioweapon defense mode"),
    "security_lock": (["security", "lock"], "Lock the vehicle"),
    "security_unlock": (["security", "unlock"], "Unlock the vehicle"),
    "security_sentry": (["security", "sentry"], "Toggle sentry mode"),
    "security_flash": (["security", "flash"], "Flash the lights"),
    "security_honk": (["security", "honk"], "Honk the horn"),
    "security_remote_start": (["security", "remote-start"], "Enable remote start"),
    "trunk_open": (["trunk", "open"], "Open the trunk"),
    "trunk_close": (["trunk", "close"], "Close the trunk"),
    "trunk_frunk": (["trunk", "frunk"], "Open the frunk"),
    "trunk_window": (["trunk", "window"], "Vent or close windows"),
    "media_play_pause": (["media", "play-pause"], "Toggle media play/pause"),
    "media_next_track": (["media", "next-track"], "Skip to next track"),
    "media_prev_track": (["media", "prev-track"], "Go to previous track"),
    "media_volume": (["media", "volume"], "Set media volume"),
    "nav_send": (["nav", "send"], "Send a destination to the vehicle"),
    "nav_supercharger": (["nav", "supercharger"], "Navigate to nearest Supercharger"),
    "software_schedule": (["software", "schedule"], "Schedule software update"),
    "software_cancel": (["software", "cancel"], "Cancel pending software update"),
    "vehicle_wake": (["vehicle", "wake"], "Wake the vehicle"),
    "vehicle_rename": (["vehicle", "rename"], "Rename the vehicle"),
    "cache_clear": (["cache", "clear"], "Clear response cache"),
}

# Commands excluded from MCP (long-running, interactive, or infrastructure)
_EXCLUDED = {
    "vehicle telemetry stream",
    "openclaw bridge",
    "auth login",
    "auth logout",
    "auth register",
    "setup",
    "mcp serve",
    "key generate",
    "key deploy",
    "key enroll",
    "key unenroll",
}


class MCPServer:
    """MCP server that wraps tescmd CLI commands as tools."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._tools: dict[str, tuple[list[str], str, bool]] = {}
        for name, (args, desc) in _READ_TOOLS.items():
            self._tools[name] = (args, desc, False)
        for name, (args, desc) in _WRITE_TOOLS.items():
            self._tools[name] = (args, desc, True)

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool descriptors."""
        tools = []
        for name, (_args, desc, is_write) in sorted(self._tools.items()):
            tool: dict[str, Any] = {
                "name": name,
                "description": desc,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "vin": {
                            "type": "string",
                            "description": "Vehicle VIN (optional if TESLA_VIN set)",
                        },
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional CLI arguments",
                        },
                    },
                },
            }
            if is_write:
                tool["annotations"] = {"readOnlyHint": False}
            else:
                tool["annotations"] = {"readOnlyHint": True}
            tools.append(tool)
        return tools

    def invoke_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool by running the corresponding CLI command.

        Returns the parsed JSON output or an error dict.
        """
        if name not in self._tools:
            return {"error": f"Unknown tool: {name}"}

        args_template, _desc, _is_write = self._tools[name]

        # Build CLI args
        cli_args = ["--format", "json", "--wake"]

        vin = arguments.get("vin")
        if vin:
            cli_args.extend(["--vin", vin])

        cli_args.extend(args_template)

        extra_args = arguments.get("args", [])
        if extra_args:
            cli_args.extend(extra_args)

        import os

        from click.testing import CliRunner

        from tescmd.cli.main import cli

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, cli_args, env=os.environ.copy())

        output = result.output.strip()
        if result.exit_code != 0:
            error_output = result.stderr.strip() if result.stderr else output
            return {
                "error": error_output or f"Command failed with exit code {result.exit_code}",
                "exit_code": result.exit_code,
            }

        # Parse JSON output
        try:
            return json.loads(output)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {"output": output}

    async def run_stdio(self) -> None:
        """Run the MCP server on stdio transport."""
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("tescmd", instructions="Tesla vehicle management via Fleet API")

        for name, (_args, desc, _is_write) in self._tools.items():
            self._register_fastmcp_tool(mcp, name, desc)

        await mcp.run_stdio_async()

    async def run_http(self, *, port: int = 8080, public_url: str | None = None) -> None:
        """Run the MCP server on streamable-http transport."""
        from urllib.parse import urlparse

        from mcp.server.auth.settings import (
            AuthSettings,
            ClientRegistrationOptions,
            RevocationOptions,
        )
        from mcp.server.fastmcp import FastMCP
        from mcp.server.transport_security import TransportSecuritySettings
        from pydantic import AnyHttpUrl

        base_url = public_url or f"http://127.0.0.1:{port}"
        provider = _InMemoryOAuthProvider(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )

        # Build allowed hosts: always include localhost, add public hostname
        # when exposed via Tailscale Funnel or similar reverse proxy.
        allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
        allowed_origins = [
            "http://127.0.0.1:*",
            "http://localhost:*",
            "http://[::1]:*",
        ]
        if public_url:
            parsed = urlparse(public_url)
            if parsed.hostname:
                allowed_hosts.append(parsed.hostname)
                allowed_hosts.append(f"{parsed.hostname}:*")
                allowed_origins.append(f"{parsed.scheme}://{parsed.hostname}")
                allowed_origins.append(f"{parsed.scheme}://{parsed.hostname}:*")

        mcp = FastMCP(
            "tescmd",
            instructions="Tesla vehicle management via Fleet API",
            host="127.0.0.1",
            port=port,
            auth_server_provider=provider,
            auth=AuthSettings(
                issuer_url=AnyHttpUrl(base_url),
                resource_server_url=AnyHttpUrl(base_url),
                client_registration_options=ClientRegistrationOptions(enabled=True),
                revocation_options=RevocationOptions(enabled=True),
            ),
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=allowed_hosts,
                allowed_origins=allowed_origins,
            ),
        )

        for name, (_args, desc, _is_write) in self._tools.items():
            self._register_fastmcp_tool(mcp, name, desc)

        await mcp.run_streamable_http_async()

    def _register_fastmcp_tool(
        self,
        mcp: Any,
        tool_name: str,
        description: str,
    ) -> None:
        """Register a single tool with the FastMCP server."""
        server = self

        @mcp.tool(name=tool_name, description=description)  # type: ignore[misc]
        def _tool(vin: str = "", args: list[str] | None = None) -> str:
            result = server.invoke_tool(tool_name, {"vin": vin, "args": args or []})
            return json.dumps(result, default=str, indent=2)


class _PermissiveClient:
    """OAuth client wrapper that accepts any redirect URI and scope.

    Used for auto-created clients on personal MCP servers where the operator
    has already consented by starting the server. Wraps the real
    ``OAuthClientInformationFull`` model but overrides validation to be
    permissive — access control is at the network layer, not the OAuth layer.
    """

    def __init__(self, *, client_id: str, client_secret: str | None = None) -> None:
        from mcp.shared.auth import OAuthClientInformationFull
        from pydantic import AnyUrl

        self._inner = OAuthClientInformationFull(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=[AnyUrl("https://placeholder.invalid")],
            token_endpoint_auth_method="client_secret_post" if client_secret else "none",
        )

    def validate_redirect_uri(self, redirect_uri: Any) -> Any:
        """Accept any redirect URI."""
        if redirect_uri is not None:
            return redirect_uri
        return self._inner.redirect_uris[0]  # type: ignore[index]

    def validate_scope(self, requested_scope: Any) -> list[str]:
        """Accept any scope."""
        if isinstance(requested_scope, str):
            return requested_scope.split()
        return []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _InMemoryOAuthProvider:
    """In-memory OAuth 2.1 authorization server for personal MCP servers.

    Auto-approves all authorization requests — access control is handled
    at the network layer (Tailscale Funnel, localhost, etc.).

    Implements the ``OAuthAuthorizationServerProvider`` protocol with
    dynamic client registration and in-memory token storage.  Unknown
    ``client_id`` values are auto-created as permissive clients so MCP
    clients that skip dynamic registration (e.g. Claude.ai) still work.
    """

    def __init__(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._configured_client_id = client_id
        self._configured_client_secret = client_secret
        self._clients: dict[str, Any] = {}
        self._auth_codes: dict[str, Any] = {}
        self._access_tokens: dict[str, Any] = {}
        self._refresh_tokens: dict[str, Any] = {}

    async def get_client(self, client_id: str) -> Any:
        client = self._clients.get(client_id)
        if client is not None:
            return client
        # Auto-create a permissive client for any unknown client_id.
        # This is safe because network-level access control (Tailscale,
        # localhost) gates who can reach the server in the first place.
        # If this is the configured client, attach the secret so token
        # endpoint authentication succeeds.
        secret = (
            self._configured_client_secret
            if client_id == self._configured_client_id
            else None
        )
        permissive = _PermissiveClient(client_id=client_id, client_secret=secret)
        self._clients[client_id] = permissive
        return permissive

    async def register_client(self, client_info: Any) -> None:
        self._clients[client_info.client_id] = client_info

    async def authorize(self, client: Any, params: Any) -> str:
        import secrets
        import time
        from urllib.parse import urlencode, urlparse, urlunparse

        from mcp.server.auth.provider import AuthorizationCode

        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + 300,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )

        parsed = urlparse(str(params.redirect_uri))
        query_parts = [parsed.query] if parsed.query else []
        extra: dict[str, str] = {"code": code}
        if params.state:
            extra["state"] = params.state
        query_parts.append(urlencode(extra))
        return urlunparse(parsed._replace(query="&".join(query_parts)))

    async def load_authorization_code(
        self,
        client: Any,
        authorization_code: str,
    ) -> Any:
        code_obj = self._auth_codes.get(authorization_code)
        if code_obj is not None and code_obj.client_id == client.client_id:
            return code_obj
        return None

    async def exchange_authorization_code(
        self,
        client: Any,
        authorization_code: Any,
    ) -> Any:
        import secrets
        import time

        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthToken

        self._auth_codes.pop(authorization_code.code, None)

        access_str = secrets.token_urlsafe(32)
        refresh_str = secrets.token_urlsafe(32)

        self._access_tokens[access_str] = AccessToken(
            token=access_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 3600,
            resource=authorization_code.resource,
        )
        self._refresh_tokens[refresh_str] = RefreshToken(
            token=refresh_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
        )

        return OAuthToken(
            access_token=access_str,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
            refresh_token=refresh_str,
        )

    async def load_access_token(self, token: str) -> Any:
        return self._access_tokens.get(token)

    async def load_refresh_token(
        self,
        client: Any,
        refresh_token: str,
    ) -> Any:
        rt = self._refresh_tokens.get(refresh_token)
        if rt is not None and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(
        self,
        client: Any,
        refresh_token: Any,
        scopes: list[str],
    ) -> Any:
        import secrets
        import time

        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthToken

        self._refresh_tokens.pop(refresh_token.token, None)

        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        used_scopes = scopes or refresh_token.scopes

        self._access_tokens[new_access] = AccessToken(
            token=new_access,
            client_id=client.client_id,
            scopes=used_scopes,
            expires_at=int(time.time()) + 3600,
        )
        self._refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=client.client_id,
            scopes=used_scopes,
        )

        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(used_scopes) if used_scopes else None,
            refresh_token=new_refresh,
        )

    async def revoke_token(self, token: Any) -> None:
        from mcp.server.auth.provider import AccessToken, RefreshToken

        if isinstance(token, AccessToken):
            self._access_tokens.pop(token.token, None)
        elif isinstance(token, RefreshToken):
            self._refresh_tokens.pop(token.token, None)


def create_mcp_server(*, client_id: str, client_secret: str) -> MCPServer:
    """Factory function to create a configured MCP server."""
    return MCPServer(client_id=client_id, client_secret=client_secret)
