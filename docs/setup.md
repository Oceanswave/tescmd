# Setup Guide

This guide walks through `tescmd setup`, the interactive first-run wizard that configures everything needed to use the Tesla Fleet API.

## Overview

The setup wizard runs in phases:

0. **Tier selection** — choose read-only or full control
1. **Domain setup** — configure a public domain for key hosting (GitHub Pages, Tailscale Funnel, or manual)
2. **Developer Portal** — create a Tesla Developer app and get credentials
3. **Key generation & deployment** — create an EC key pair and host the public key (full tier only)
3.5. **Key enrollment** — add the key to your vehicle via the Tesla app (full tier only)
4. **Fleet API registration** — register your app with Tesla (`POST /api/1/partner_accounts`)
5. **OAuth login** — authenticate via browser
6. **Summary** — recap of configuration and next steps

Run it with:

```bash
tescmd setup
```

The wizard is safe to re-run — it skips completed steps, detects existing configuration, and lets you upgrade from read-only to full control. Each phase checks prerequisites and offers remediation if something is missing.

### Prerequisites

- **Python 3.11+** — tescmd requires modern typing features
- **Git** — version control, repo management
- **GitHub CLI** (`gh`) — recommended for key hosting via GitHub Pages (`gh auth login`)
- **Tailscale** — optional for key hosting and required for telemetry streaming (`tailscale login`)

Without GitHub CLI or Tailscale, you'll need to manually host your public key on your own domain.

### Environment Variables

The wizard stores configuration in your `.env` file. These variables control setup behavior:

| Variable | Description |
|---|---|
| `TESLA_SETUP_TIER` | `readonly` or `full` — controls which phases run |
| `TESLA_DOMAIN` | Your registered domain (set by the wizard) |
| `TESLA_HOSTING_METHOD` | `github` or `tailscale` — how the public key is hosted |
| `TESLA_GITHUB_REPO` | GitHub Pages repo (e.g., `username/username.github.io`) |
| `TESLA_CLIENT_ID` | OAuth2 client ID from the Tesla Developer Portal |
| `TESLA_CLIENT_SECRET` | OAuth2 client secret |
| `TESLA_REGION` | API region: `na`, `eu`, `cn` |

---

## Phase 0: Tier Selection

**Read-only** lets you view vehicle data (battery, location, climate, etc.) without sending commands. **Full control** adds lock/unlock, charge control, climate, trunk, media, navigation, and enables Fleet Telemetry streaming.

| Capability | Read-only | Full control |
|---|---|---|
| Vehicle data queries | Yes | Yes |
| Energy product queries | Yes | Yes |
| Vehicle commands | No | Yes |
| Fleet Telemetry streaming | No | Yes |
| Requires EC key pair | No | Yes |

You can upgrade from read-only to full control later by running `tescmd setup` again.

---

## Phase 1: Domain Setup

Tesla requires every Fleet API app to have a registered domain where the public key is hosted at a specific path:

```
https://<your-domain>/.well-known/appspecific/com.tesla.3p.public-key.pem
```

The setup wizard detects available hosting methods and offers them in priority order. Before deploying a new key, it checks whether a public key already exists at the `.well-known` URL to avoid unnecessary redeployment.

> **Important: domain choice affects telemetry streaming.** If you plan to use `tescmd vehicle telemetry stream`, note that key hosting and telemetry streaming are separate concerns. Key hosting uses your registered domain (GitHub Pages or Tailscale), while telemetry streaming requires **Tailscale Funnel** to expose your local WebSocket server.

### Method 1: GitHub Pages (recommended for key hosting only)

**Requires:** `gh` CLI installed and authenticated (`gh auth login`)

- **Always-on** — survives machine reboots and shutdowns
- **Free** — GitHub Pages is free for public repos
- **Automatic** — the wizard creates the repo, deploys the key, and waits for it to go live
- **No telemetry streaming** — GitHub Pages cannot serve as a Fleet Telemetry server; choose Tailscale if you need streaming

The wizard creates `<username>.github.io` if it doesn't exist, commits the public key to the `.well-known/appspecific/` path, and configures Jekyll to serve the directory (via an `_config.yml` include rule).

### Method 2: Tailscale Funnel (recommended for telemetry streaming)

**Requires:** Tailscale installed, running, authenticated, and Funnel enabled in your tailnet ACL policy

- **Machine-dependent** — if your machine is off or Tailscale stops, Tesla cannot fetch the key
- **Domain is machine-specific** — your domain is `<machine>.tailnet.ts.net`, so changing machines means re-registering
- **Enables telemetry streaming** — the same Tailscale hostname serves both your public key and the telemetry WebSocket server, satisfying Tesla's domain-matching requirement
- **Good for development** — fast setup, no GitHub account needed

The wizard runs `tailscale serve` to host the key directory and `tailscale funnel` to make it publicly accessible.

### Method 3: Manual

You provide your own domain and are responsible for hosting the public key at the `.well-known` path. Use this if you have your own web server or CDN.

After entering your domain, the wizard stores it in your `.env` file as `TESLA_DOMAIN`.

---

## Phase 2: Developer Portal

You need a Tesla Developer app to get OAuth credentials.

1. Go to [developer.tesla.com](https://developer.tesla.com)
2. Create a new application
3. Set the **Allowed Origin URL** to `https://<your-domain>` (the domain from Phase 1)
   - For telemetry streaming, add your Tailscale hostname as an additional origin:
     `https://<your-machine>.tailnet.ts.net`
4. Set the **Redirect URI** to `http://localhost:8085/callback`
5. Copy the **Client ID** and **Client Secret**

The wizard prompts for these values and offers to store them in your `.env` file (you can decline if you prefer to manage credentials manually).

---

## Phase 3: Key Generation & Deployment

For full-control tier, the wizard generates an EC P-256 key pair:

- **Private key** — stored at `~/.config/tescmd/keys/private_key.pem` with restricted permissions (0600)
- **Public key** — stored at `~/.config/tescmd/keys/public_key.pem` and deployed to your domain

The public key is what Tesla fetches during registration and what vehicles use to verify signed commands. The private key never leaves your machine.

The deployment method matches what was chosen in Phase 1:

- **GitHub Pages**: commits and pushes the key to your `*.github.io` repo
- **Tailscale Funnel**: writes the key to `~/.config/tescmd/serve/` and starts serve + funnel
- **Manual**: shows the key path and the URL where you need to host it

---

## Phase 3.5: Key Enrollment

Enrollment adds your key to a specific vehicle. Each vehicle must be enrolled separately.

1. The wizard opens `https://tesla.com/_ak/<your-domain>` in your browser
2. Open this URL **on your phone** (not desktop)
3. Tap **Finish Setup** on the web page
4. The Tesla app shows an **Add Virtual Key** prompt
5. Approve it

If the prompt doesn't appear, force-quit the Tesla app, go back to your browser, and tap Finish Setup again.

After enrollment, signed commands work automatically for that vehicle.

---

## Phase 4: Fleet API Registration

The wizard calls `POST /api/1/partner_accounts` to register your app with Tesla's Fleet API. This uses a client-credentials grant to obtain a partner token, then registers your domain.

**Common errors:**

- **HTTP 412 (origin mismatch)**: The Allowed Origin URL in your Tesla Developer app doesn't match your domain. Fix it at [developer.tesla.com](https://developer.tesla.com).
- **HTTP 424 (public key not found)**: Tesla couldn't fetch your public key. Verify it's accessible with `tescmd key validate`.

---

## Phase 5: OAuth Login

The wizard opens your browser for Tesla's OAuth2 PKCE flow. Click **Select All** to grant all scopes, then **Allow**.

If you previously granted a narrower set of scopes, the wizard uses `--reconsent` to prompt Tesla to show any new scopes not yet approved.

Tokens are stored in your OS keyring (macOS Keychain, GNOME Keyring, Windows Credential Manager) or fall back to `~/.config/tescmd/tokens.json` on headless systems. See [authentication.md](authentication.md) for details on token storage backends.

---

## Phase 6: Summary

The wizard displays a recap of your configuration:

- Tier (read-only or full control)
- Domain and hosting method
- Key file locations (full tier)
- Enrolled vehicles (full tier)
- Token storage backend
- Suggested next commands (e.g., `tescmd charge status`, `tescmd vehicle list`)

---

## Troubleshooting

### Key not accessible after deployment

```bash
# Check key accessibility
tescmd key validate

# Re-deploy if needed
tescmd key deploy
tescmd key deploy --method tailscale  # force Tailscale method
```

For GitHub Pages, it can take 1-3 minutes for the first deployment to propagate. For Tailscale, verify that Funnel is enabled in your tailnet ACL policy.

### Registration fails with HTTP 412

Your Allowed Origin URL at [developer.tesla.com](https://developer.tesla.com) must exactly match `https://<your-domain>`. Check for typos, trailing slashes, or case mismatches (Tesla rejects uppercase).

### Registration fails with HTTP 424

Tesla couldn't download your public key. Run `tescmd key validate` to check if it's accessible. If using Tailscale, ensure your machine is on and Tailscale is running.

### Enrollment prompt doesn't appear

1. Force-quit the Tesla app completely
2. Re-open the enrollment URL on your phone
3. Tap Finish Setup again
4. The Tesla app should now show the Add Virtual Key prompt

### Token refresh fails

```bash
tescmd auth refresh     # try refreshing
tescmd auth logout      # clear tokens
tescmd auth login       # re-authenticate
```
