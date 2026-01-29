# Authentication

tescmd uses Tesla's OAuth2 flow with PKCE for user authentication, and EC key pairs for vehicle command authorization. This document covers the full lifecycle.

## Overview

There are two separate auth concerns:

1. **OAuth2 tokens** — identify the user to Tesla's Fleet API (required for all API calls, both commands and data queries)
2. **EC key pairs** — authorize signed commands to the vehicle (required for vehicle commands; not needed for read-only data queries)

Most users only need OAuth2. Key enrollment is required for command signing on newer vehicles using the vehicle command protocol.

## OAuth2 PKCE Flow

### Prerequisites

You need a Tesla Developer account and a registered application:

1. Go to [developer.tesla.com](https://developer.tesla.com)
2. Create an application
3. Note your **Client ID** and **Client Secret**
4. Set the redirect URI to `http://localhost:8085/callback` (tescmd's default)

### Login

```bash
tescmd auth login
```

This runs an interactive OAuth2 PKCE flow:

```
Step 1: tescmd generates a PKCE code_verifier (random 128-byte string)
        and derives a code_challenge (SHA-256 hash, base64url-encoded)

Step 2: tescmd starts a local HTTP server on localhost:8085

Step 3: tescmd opens the system browser to Tesla's authorization endpoint:
        https://auth.tesla.com/oauth2/v3/authorize
        ?client_id=<CLIENT_ID>
        &redirect_uri=http://localhost:8085/callback
        &response_type=code
        &scope=openid vehicle_device_data vehicle_cmds vehicle_charging_cmds
        &code_challenge=<CHALLENGE>
        &code_challenge_method=S256
        &state=<RANDOM>

Step 4: User logs in to Tesla account in the browser
        and grants permissions to the application

Step 5: Tesla redirects to http://localhost:8085/callback?code=<AUTH_CODE>&state=<STATE>
        tescmd's local server captures the authorization code

Step 6: tescmd exchanges the code for tokens:
        POST https://auth.tesla.com/oauth2/v3/token
        {
          "grant_type": "authorization_code",
          "client_id": "<CLIENT_ID>",
          "client_secret": "<CLIENT_SECRET>",
          "code": "<AUTH_CODE>",
          "code_verifier": "<VERIFIER>",
          "redirect_uri": "http://localhost:8085/callback"
        }

Step 7: Tesla returns access_token, refresh_token, expires_in, id_token

Step 8: tescmd stores tokens in the OS keyring
```

### Scopes

tescmd requests these OAuth2 scopes:

| Scope | Purpose |
|---|---|
| `openid` | User identity |
| `vehicle_device_data` | Read vehicle state (location, battery, climate, etc.) |
| `vehicle_cmds` | Send commands (lock, unlock, climate, etc.) |
| `vehicle_charging_cmds` | Charging commands (start, stop, schedule) |
| `energy_device_data` | Energy product data (Powerwall, Solar) |
| `offline_access` | Refresh token for long-lived sessions |

### Token Management

**Storage:** Tokens are stored in the OS keyring via the `keyring` library:
- macOS: Keychain
- Linux: GNOME Keyring / KWallet / SecretService
- Windows: Windows Credential Locker

**Refresh:** Access tokens expire (typically 8 hours). tescmd automatically refreshes using the refresh token when a 401 response is received. The refresh is transparent — the original request is retried with the new token.

**Manual refresh:**
```bash
tescmd auth refresh
```

**Check status:**
```bash
tescmd auth status
```

Displays: token expiry time, scopes, associated region, and whether refresh token is available.

**Logout:**
```bash
tescmd auth logout
```

Removes tokens from the keyring. Does not revoke the tokens server-side (Tesla's API does not support token revocation).

## Token Storage Details

```
Keyring entries (per profile):
  service: tescmd
  username: <profile_name>/access_token
  password: <access_token_value>

  service: tescmd
  username: <profile_name>/refresh_token
  password: <refresh_token_value>

  service: tescmd
  username: <profile_name>/token_meta
  password: <json: {expires_at, scopes, region}>
```

## EC Key Pairs

### Why Keys?

Tesla's newer vehicle command protocol requires commands to be signed with an EC key that has been registered (enrolled) on the vehicle. This is separate from OAuth2 — the OAuth token identifies the user, while the EC signature proves the command came from a trusted device.

**Read-only operations** (vehicle data, location, battery status) do **not** require key enrollment — they only need a valid OAuth token.

### Key Generation

```bash
tescmd key generate
```

Generates a P-256 (secp256r1) EC key pair and stores it:
- Private key: `~/.config/tescmd/keys/private_key.pem`
- Public key: `~/.config/tescmd/keys/public_key.pem`

### Key Enrollment

The public key must be enrolled on the vehicle. There are two methods:

#### Method 1: Tesla Developer Portal (recommended)

Works remotely — no physical proximity to the vehicle required:

```bash
tescmd key register --portal
```

This:
1. Opens the Tesla Developer Portal in your browser
2. Guides you to register the public key for your application
3. Tesla sends the key to the vehicle over its cellular connection
4. The vehicle owner confirms enrollment via the Tesla mobile app
5. Key is now trusted for command signing

This is the recommended method for most users and the only method for fleet deployments.

#### Method 2: BLE Enrollment (alternative)

Requires physical proximity to the vehicle (Bluetooth range). Useful when the vehicle has no cellular connectivity or for offline provisioning:

```bash
tescmd key register --ble
```

This:
1. Scans for nearby Tesla vehicles via BLE
2. Presents a picker if multiple vehicles are found
3. Sends the public key to the vehicle over BLE
4. The vehicle displays a confirmation on its touchscreen
5. User confirms enrollment on the vehicle screen
6. Key is now trusted for command signing

Requires the `bleak` package (included in default install).

### Key Usage

Once enrolled, tescmd automatically signs vehicle commands with the private key. This is transparent — the `CommandAPI` layer handles signing via `crypto/signing.py`.

```
Command flow with signing:

  1. CommandAPI builds command payload
  2. crypto/signing.py signs payload with private key
  3. Signed payload sent via Fleet API
  4. Vehicle verifies signature against enrolled public key
  5. Command executes
```

## Headless Authentication

For servers and bots that can't open a browser, use environment-based auth:

### Option 1: Pre-obtained Tokens

Obtain tokens on a machine with a browser, then transfer:

```bash
# On machine with browser
tescmd auth login
tescmd auth export > tokens.json  # exports tokens as JSON

# On headless machine
tescmd auth import < tokens.json
```

### Option 2: Direct Environment Variables

If you manage tokens externally:

```dotenv
TESLA_ACCESS_TOKEN=eyJ...
TESLA_REFRESH_TOKEN=eyJ...
```

When `TESLA_ACCESS_TOKEN` is set, tescmd uses it directly without checking the keyring.

## Multi-Profile Authentication

Each profile has its own token set:

```bash
# Login to default profile
tescmd auth login

# Login to a different profile
tescmd --profile work-car auth login

# Check status of a specific profile
tescmd --profile work-car auth status
```

Profiles are independent — different Tesla accounts, different regions, different vehicles.

## Security Considerations

- **Tokens in keyring** — never stored in plaintext config files
- **Client secret in `.env`** — gitignored, not in config.toml
- **Private keys file-permission protected** — `chmod 600` on generation
- **PKCE** — prevents authorization code interception
- **State parameter** — prevents CSRF in OAuth flow
- **Local callback server** — binds to localhost only, ephemeral port option available
