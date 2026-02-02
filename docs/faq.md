# Frequently Asked Questions

## General

### What's the difference between read-only and full tier?

**Read-only** lets you query vehicle data (battery, location, climate state, etc.) and energy product data. **Full control** adds vehicle commands (lock/unlock, charge control, climate, trunk, media, navigation) and enables Fleet Telemetry streaming. Full control requires an EC key pair deployed to your domain.

### Why does tescmd need a domain?

Tesla requires every Fleet API application to host its public key at a `.well-known` URL on a registered domain. Tesla fetches this key during registration and vehicles use it to verify signed commands. The domain is part of Tesla's trust model for third-party apps.

### Is my public key sensitive?

No. The public key is a *public* key by design -- it's meant to be freely distributed. Anyone can see it, and that's fine. It can only *verify* commands, not *create* them. Your private key (which stays on your machine) is the sensitive part.

### Can I use tescmd without GitHub?

Yes. GitHub Pages is the recommended hosting method because it's always-on and free, but you can also use Tailscale Funnel or host the key on your own domain. Run `tescmd setup` and it will detect available methods.

### What's the easiest way to get started?

Run `tescmd setup`. The interactive wizard handles everything from zero to a working CLI: creating a Tesla Developer app, generating an EC key pair, hosting the public key (via GitHub Pages or Tailscale Funnel), registering with the Fleet API, authenticating via OAuth2, and enrolling your key on a vehicle. Each step checks prerequisites and offers remediation if something is missing. The wizard is safe to re-run — it skips completed steps and lets you upgrade from read-only to full control.

### What Python version do I need?

Python 3.11 or newer. tescmd uses `tomllib`, `StrEnum`, and modern typing features that require 3.11+.

## Costs

### Why does tescmd prompt before waking my vehicle?

Tesla charges for every API call that returns a status code below 500, including wake requests. Wake calls are the most expensive category and are rate-limited to 3/minute. The prompt lets you wake the vehicle for free via the Tesla app instead. Use `--wake` to skip the prompt in scripts.

### How much does the Tesla Fleet API cost?

Tesla's Fleet API is pay-per-use with no free tier. Pricing varies by endpoint category. Wake requests are the most expensive, followed by vehicle commands, then data queries. See [Tesla Fleet API Billing and Limits](https://developer.tesla.com/docs/fleet-api/billing-and-limits) for current pricing.

tescmd reduces costs through universal response caching, smart wake state tracking, and wake confirmation prompts. A typical battery check that would cost 4+ API calls without protections costs 2 calls with tescmd's interactive prompt (the initial 408 is unavoidable, plus the successful retry after waking via the Tesla app for free). Subsequent checks within the cache TTL cost 0 calls. See [docs/api-costs.md](api-costs.md) for detailed cost breakdowns.

## Vehicles

### Can I use tescmd with multiple vehicles?

Yes. Most commands accept a VIN as a positional argument or via `--vin`. If you don't specify a VIN, tescmd uses the default from `TESLA_VIN` or offers an interactive picker. Each vehicle needs its own key enrollment (`tescmd key enroll <VIN>`), but the same key pair works for all vehicles on your account.

### Why is my vehicle showing as asleep?

Tesla vehicles enter sleep mode to conserve battery. Most data queries require the vehicle to be awake. tescmd caches responses so repeated queries don't require the vehicle to stay awake. When the vehicle is asleep, tescmd prompts before sending a billable wake call -- you can wake it for free via the Tesla app and retry.

### What's Vehicle Command Protocol?

The Vehicle Command Protocol is Tesla's newer system for sending commands to vehicles. It uses ECDH key exchange and HMAC-SHA256 signing via protobuf messages sent to the `signed_command` endpoint. tescmd handles this transparently -- once your key is enrolled, commands are automatically signed. The `command_protocol` setting (`auto`/`signed`/`unsigned`) controls this behavior.

## Configuration

### How do I switch between US and metric units?

```bash
tescmd --units metric charge status    # all metric: C, km, bar
tescmd --units us charge status       # all US: F, mi, psi (default)
```

Or set individual units via environment variables: `TESLA_TEMP_UNIT`, `TESLA_DISTANCE_UNIT`, `TESLA_PRESSURE_UNIT`.

### What data does tescmd cache and where?

All read commands are cached under `~/.cache/tescmd/` as JSON files. Each entry has a TTL based on how frequently the data changes:

| Data type | TTL | Examples |
|---|---|---|
| Static | 1 hour | specs, warranty, options |
| Slow-changing | 5 minutes | vehicle list, fleet status |
| Standard | 1 minute | vehicle data, charge state |
| Location-dependent | 30 seconds | nearby chargers |

Write commands are never cached but automatically invalidate the relevant cache entries. Use `tescmd cache status` to see cache statistics and `tescmd cache clear` to clear it.

### Can AI agents use tescmd?

Yes. tescmd is designed for agent use in two ways:

1. **Direct CLI invocation** — agents call `tescmd` commands with `--format json` and parse the structured JSON output. Piped/non-TTY mode automatically emits JSON. Exit codes are meaningful, and the `--wake` flag controls billing. See [docs/bot-integration.md](bot-integration.md) for the full JSON schema and headless auth setup.

2. **MCP server** — `tescmd mcp serve` exposes all commands as MCP tools. Claude.ai, Claude Desktop, Claude Code, and other MCP-compatible agents connect directly and call tools without parsing CLI output. The HTTP transport supports OAuth 2.1 (auto-approved), and stdio transport works as a subprocess. See [docs/mcp.md](mcp.md) for setup instructions.

In both modes, the cache means agents can query as often as needed without cost concerns.

### What is the MCP server and how do I use it?

The MCP (Model Context Protocol) server lets AI agents interact with your Tesla through standardized tools instead of invoking CLI commands. Start it with `tescmd mcp serve`. The server exposes ~70 tools (read + write) that mirror every CLI command, with structured JSON responses.

For Claude Desktop or Claude Code, add tescmd to your MCP server config using stdio transport. For Claude.ai or remote agents, use the HTTP transport (optionally exposed via Tailscale Funnel). The server handles OAuth 2.1 authentication automatically. See [docs/mcp.md](mcp.md) for full configuration examples.

### What is the OpenClaw bridge?

The OpenClaw bridge (`tescmd openclaw bridge`) streams filtered vehicle telemetry to an [OpenClaw](https://openclaw.ai/) Gateway for real-time agent consumption. Unlike raw telemetry streaming, the bridge applies dual-gate filtering — each field must exceed both a delta threshold (value change) AND a throttle interval (minimum time between emissions) — to reduce noise and control event volume. This means agents receive only meaningful state changes rather than a firehose of raw data. See [docs/openclaw.md](openclaw.md) for configuration details.

## Hosting & Deployment

### Can I use Tailscale Funnel for key hosting?

Yes. If Tailscale is installed and Funnel is enabled in your tailnet ACL, `tescmd setup` offers it as a hosting option. Your key is served at `https://<machine>.tailnet.ts.net/.well-known/appspecific/com.tesla.3p.public-key.pem`.

**Trade-off**: Tailscale requires your machine to be running. If it's off, Tesla can't reach your key. This is fine for development but consider GitHub Pages for always-on hosting.

### Can I stream telemetry without Tailscale?

Not currently. Telemetry streaming requires Tailscale Funnel to expose a publicly reachable HTTPS endpoint for Tesla's fleet telemetry push. Tailscale handles NAT traversal and TLS termination automatically.

### Does tescmd work behind a firewall?

For vehicle data queries and commands, tescmd only needs outbound HTTPS access to Tesla's API servers. For key hosting via Tailscale Funnel, Tailscale handles NAT traversal automatically -- no port forwarding needed. For GitHub Pages, the key is hosted on GitHub's infrastructure.

### How do I uninstall or revoke access?

```bash
# Remove the virtual key from your vehicle
tescmd key unenroll

# Clear local tokens
tescmd auth logout

# Clear cached data
tescmd cache clear
```

The `key unenroll` command shows three methods: vehicle touchscreen (immediate), Tesla app (may take up to 2 hours), or Tesla account website. It can also open the OAuth consent revocation page to fully revoke app access.
