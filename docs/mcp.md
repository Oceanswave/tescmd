# MCP Server

tescmd includes a built-in [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server that exposes all CLI commands as tools. AI agents like Claude Desktop and Claude Code can connect to this server and query or control Tesla vehicles programmatically.

> **Recommended:** Use `tescmd serve` instead of `tescmd mcp serve` for most use cases. `tescmd serve` combines the MCP server with telemetry-driven cache warming, so agent reads are free while telemetry is active. See [When to Use Which](#when-to-use-which) below.

## Quick Start

```bash
# Recommended: MCP + telemetry cache warming
tescmd serve 5YJ3...

# MCP-only (same as tescmd mcp serve)
tescmd serve --no-telemetry

# stdio transport for Claude Desktop
tescmd serve --transport stdio

# Legacy: standalone MCP server
tescmd mcp serve
```

## When to Use Which

| Command | MCP | Telemetry | Cache Warming | OpenClaw | Best For |
|---|---|---|---|---|---|
| `tescmd serve VIN` | yes | yes | yes | optional | Production agent use |
| `tescmd serve --no-telemetry` | yes | - | - | - | Simple MCP-only setup |
| `tescmd serve --transport stdio` | yes (stdio) | - | - | - | Claude Desktop/Code subprocess |
| `tescmd serve VIN --no-mcp` | - | yes | - | optional | Telemetry dashboard/monitoring |
| `tescmd mcp serve` | yes | - | - | - | Lightweight MCP (legacy alias) |
| `tescmd openclaw bridge` | - | yes | - | yes | Dedicated OpenClaw bridge |
| `tescmd vehicle telemetry stream` | - | yes | - | - | Interactive telemetry dashboard |

## CLI Options

```
tescmd mcp serve [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--transport` | `streamable-http` or `stdio` | `streamable-http` |
| `--port PORT` | HTTP port (streamable-http only) | `8080` |
| `--tailscale` | Expose via Tailscale Funnel | off |
| `--client-id` | MCP client ID (env: `TESCMD_MCP_CLIENT_ID`) | required |
| `--client-secret` | MCP client secret (env: `TESCMD_MCP_CLIENT_SECRET`) | required |

## Authentication

All transports require MCP client credentials. Set them via environment variables or CLI flags:

```bash
export TESCMD_MCP_CLIENT_ID="my-agent"
export TESCMD_MCP_CLIENT_SECRET="a-strong-random-secret"
```

Or pass them directly:

```bash
tescmd mcp serve --client-id my-agent --client-secret a-strong-random-secret
```

**HTTP transport (streamable-http):** The server implements the full MCP OAuth 2.1 specification. Clients authenticate via an authorization code flow with PKCE:

1. Client connects to `/mcp` — receives `401 Unauthorized`
2. Client discovers OAuth endpoints via `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`
3. Client optionally registers via `/register` (dynamic client registration is enabled)
4. Client redirects to `/authorize` — the server auto-approves and redirects back with an authorization code
5. Client exchanges the code at `/token` for an access token
6. Client uses `Authorization: Bearer <access_token>` on subsequent `/mcp` requests

MCP clients like Claude.ai handle this flow automatically — you just provide the server URL, client ID, and client secret in the connection settings.

For clients that skip dynamic registration (e.g. Claude.ai without OAuth credentials specified), the server auto-creates a permissive client entry for any `client_id` that arrives. When the `client_id` matches the configured `TESCMD_MCP_CLIENT_ID`, the server uses the matching `TESCMD_MCP_CLIENT_SECRET` for token endpoint authentication.

Access control is handled at the network layer (Tailscale Funnel, localhost binding) rather than the OAuth layer — the OAuth flow exists to satisfy the MCP protocol, not to gate access.

**stdio transport:** Credentials are required for consistency but are not validated on the wire (stdio is a local subprocess pipe with no HTTP layer).

## Agent Setup

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tescmd": {
      "command": "tescmd",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "TESCMD_MCP_CLIENT_ID": "claude-desktop",
        "TESCMD_MCP_CLIENT_SECRET": "your-secret-here"
      }
    }
  }
}
```

### Claude Code

Add to `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "tescmd": {
      "command": "tescmd",
      "args": ["serve", "--transport", "stdio"],
      "env": {
        "TESCMD_MCP_CLIENT_ID": "claude-code",
        "TESCMD_MCP_CLIENT_SECRET": "your-secret-here"
      }
    }
  }
}
```

For a remote HTTP server (e.g. exposed via Tailscale Funnel), use the `url` form. The OAuth flow is handled automatically by Claude Code:

```json
{
  "mcpServers": {
    "tescmd": {
      "type": "streamable-http",
      "url": "https://your-machine.tailnet.ts.net/mcp"
    }
  }
}
```

### Claude.ai (Web)

Claude.ai connects to remote MCP servers via the web UI. Add the server in your Claude.ai settings:

1. Go to **Settings → MCP Servers → Add Server**
2. Enter the server URL: `https://your-machine.tailnet.ts.net/mcp`
3. Enter the client ID and client secret (matching `TESCMD_MCP_CLIENT_ID` / `TESCMD_MCP_CLIENT_SECRET`)
4. Claude.ai handles the OAuth 2.1 flow automatically — you'll see the connection succeed in the server logs

### Remote / Multi-Client

For scenarios where multiple agents connect to a single tescmd instance, use HTTP transport:

```bash
tescmd mcp serve --port 8080
```

Agents connect to `http://127.0.0.1:8080/mcp` using the streamable-http MCP transport. The server handles OAuth 2.1 automatically — clients that support the MCP auth spec will complete the authorization flow without manual configuration.

## How It Works

Each MCP tool invokes the corresponding tescmd CLI command internally via Click's `CliRunner`. Every invocation runs with `--format json --wake`, which means:

- All responses are structured JSON (the standard tescmd JSON envelope)
- Vehicles are auto-woken if asleep (billable API call)
- Response caching is active (cached reads are instant and free)
- Authentication, error handling, and all CLI behavior work identically to running tescmd directly

This design guarantees behavioral parity -- there is no separate API client or code path for MCP. If a command works via `tescmd` on the command line, it works identically as an MCP tool.

## Available Tools

### Read Tools (~30)

Read tools are annotated with `readOnlyHint: true`. They query vehicle and account state without side effects.

| Tool | Command | Description |
|------|---------|-------------|
| `vehicle_list` | `vehicle list` | List all vehicles on the account |
| `vehicle_info` | `vehicle info` | Get vehicle info summary |
| `vehicle_data` | `vehicle data` | Get full vehicle data |
| `vehicle_location` | `vehicle location` | Get vehicle location |
| `vehicle_alerts` | `vehicle alerts` | Get vehicle alerts |
| `vehicle_nearby_chargers` | `vehicle nearby-chargers` | Find nearby chargers |
| `vehicle_specs` | `vehicle specs` | Get vehicle specifications |
| `vehicle_fleet_status` | `vehicle fleet-status` | Get fleet telemetry status |
| `charge_status` | `charge status` | Get charge status |
| `climate_status` | `climate status` | Get climate status |
| `security_status` | `security status` | Get security/lock status |
| `software_status` | `software status` | Get software update status |
| `energy_list` | `energy list` | List energy products (Powerwall) |
| `energy_status` | `energy status` | Get energy site status |
| `energy_live` | `energy live` | Get live power flow data |
| `billing_history` | `billing history` | Get Supercharger billing history |
| `user_me` | `user me` | Get account info |
| `cache_status` | `cache status` | Get cache status |
| `auth_status` | `auth status` | Get auth/token status |

### Write Tools (~40)

Write tools send commands to the vehicle. They are annotated with `readOnlyHint: false`.

| Tool | Command | Description |
|------|---------|-------------|
| `vehicle_wake` | `vehicle wake` | Wake the vehicle |
| `charge_start` | `charge start` | Start charging |
| `charge_stop` | `charge stop` | Stop charging |
| `charge_limit` | `charge limit` | Set charge limit (percentage) |
| `climate_on` | `climate on` | Turn on climate control |
| `climate_off` | `climate off` | Turn off climate control |
| `climate_set` | `climate set` | Set climate temperature |
| `security_lock` | `security lock` | Lock the vehicle |
| `security_unlock` | `security unlock` | Unlock the vehicle |
| `security_sentry` | `security sentry` | Toggle sentry mode |
| `security_flash` | `security flash` | Flash the lights |
| `security_honk` | `security honk` | Honk the horn |
| `trunk_open` | `trunk open` | Open the trunk |
| `trunk_frunk` | `trunk frunk` | Open the frunk |
| `nav_send` | `nav send` | Send destination to vehicle |
| `media_play_pause` | `media play-pause` | Toggle media play/pause |
| `software_schedule` | `software schedule` | Schedule software update |
| `cache_clear` | `cache clear` | Clear response cache |

### Excluded Commands

The following commands are excluded from MCP because they are long-running, interactive, or infrastructure operations:

- `vehicle telemetry stream` -- long-running telemetry session
- `openclaw bridge` -- long-running bridge process
- `auth login` / `auth logout` / `auth register` -- requires browser interaction
- `setup` -- interactive wizard
- `mcp serve` -- the MCP server itself
- `key generate` / `key deploy` / `key enroll` / `key unenroll` -- key management operations

## Tool Parameters

Every tool accepts two optional parameters:

```json
{
  "vin": "5YJ3E1EA1NF000000",
  "args": ["--limit", "80"]
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `vin` | string | Vehicle VIN. Optional if `TESLA_VIN` is set. |
| `args` | string[] | Additional CLI arguments passed to the command. |

The `args` array maps directly to CLI flags. For example, to set the charge limit to 80%:

```json
{"name": "charge_limit", "arguments": {"vin": "5YJ3...", "args": ["80"]}}
```

## Response Format

Tool responses are the standard tescmd JSON envelope:

```json
{
  "ok": true,
  "command": "charge.status",
  "data": {
    "battery_level": 72,
    "charging_state": "Disconnected",
    "charge_limit_soc": 80
  },
  "timestamp": "2026-01-31T10:30:00Z"
}
```

Error responses:

```json
{
  "ok": false,
  "command": "charge.start",
  "error": {
    "code": "vehicle_asleep",
    "message": "Vehicle is asleep. Wake it first."
  },
  "timestamp": "2026-01-31T10:30:00Z"
}
```

## Transports

### Streamable HTTP (default)

Starts an HTTP server on `127.0.0.1:PORT/mcp`. Multiple agents can connect simultaneously. The server runs until Ctrl+C.

```bash
tescmd mcp serve --port 8080
```

### stdio

Reads JSON-RPC from stdin and writes responses to stdout. Used by Claude Desktop and Claude Code when tescmd is configured as a subprocess in their MCP server config.

```bash
tescmd mcp serve --transport stdio
```

## Tailscale Funnel

Expose the MCP server publicly over HTTPS using Tailscale Funnel. This lets remote agents connect without port forwarding or firewall changes.

```bash
tescmd mcp serve --tailscale
```

The server starts on `127.0.0.1:8080`, Tailscale Funnel creates a public `https://<hostname>.tailnet.ts.net/mcp` URL, and the public URL is printed at startup.

**Requirements:** Tailscale installed, running, and authenticated with Funnel enabled in your tailnet ACL.

**Cannot be combined with `--transport stdio`** (stdio is a local pipe, not an HTTP endpoint).

The server automatically configures DNS rebinding protection to accept the Tailscale Funnel hostname alongside localhost.

Connect from Claude.ai or Claude Code using the public URL printed at startup. The OAuth 2.1 flow is handled automatically — no manual token configuration needed.

## Tesla Authentication

The MCP server uses whatever Tesla authentication is configured for tescmd. Before starting the server, ensure you have a valid token:

```bash
# Check auth status
tescmd auth status

# Login if needed
tescmd auth login
```

The server inherits all tescmd configuration: environment variables, `.env` files, config profiles, and token storage.
