# Command Reference

Reference for all currently implemented tescmd commands. Commands fall into two categories:

- **Queries** — read vehicle state (location, battery, temperature, etc.). Require OAuth token only.
- **Actions** — send commands to the vehicle (wake, key enrollment). Require OAuth token and may require enrolled EC key.

> **Note:** Vehicle command groups (charge, climate, security, media, nav, trunk, software, fleet, raw) are planned but not yet implemented. See the roadmap section at the bottom.

## Global Options

These options apply to all commands:

```
--vin VIN           Vehicle Identification Number (overrides profile default)
--profile NAME      Use named config profile (default: "default")
--format FORMAT     Output format: rich, json, quiet (default: auto-detect)
--quiet             Shorthand for --format quiet
--region REGION     API region: na, eu, cn (default: from profile or "na")
--verbose           Enable debug logging to stderr
--help              Show help for any command or subcommand
```

## VIN Resolution

Many commands require a vehicle VIN. tescmd resolves it in order:

1. Positional argument: `tescmd vehicle info 5YJ3E1EA1NF000000`
2. `--vin` flag: `tescmd vehicle info --vin 5YJ3E1EA1NF000000`
3. `TESLA_VIN` environment variable
4. Profile default: `vin` field in active config profile
5. Interactive picker: lists your vehicles and prompts you to choose

---

## `setup` — First-Run Configuration

Interactive, tiered onboarding wizard that walks you through everything needed to start using tescmd. Running `tescmd setup` handles the entire bootstrapping process from zero to working CLI — domain provisioning, Tesla Developer Portal credentials, key generation, Fleet API registration, and OAuth login — with clear guidance and automatic error remediation at each step.

```bash
tescmd setup
```

### Tier Selection (Phase 0)

The wizard starts by asking how you want to use tescmd:

1. **Read-only** — view vehicle data, location, battery status. Requires a Tesla Developer app and a registered domain.
2. **Full control** — everything in read-only, plus lock/unlock, charge, climate, etc. Additionally requires an EC key pair deployed to your domain.

If you've previously run setup, the wizard remembers your tier and offers to upgrade from read-only to full control.

### Domain Setup (Phase 1)

Tesla requires a registered domain for Fleet API access. The wizard offers two paths:

- **Automated (recommended):** If the GitHub CLI (`gh`) is installed and authenticated, the wizard auto-creates a `<username>.github.io` GitHub Pages site and configures it as your domain. No manual steps needed.
- **Manual:** Enter your own domain. You'll need to host the `.well-known/appspecific/com.tesla.3p.public-key.pem` file yourself.

The domain is persisted to `~/.config/tescmd/.env` as `TESLA_DOMAIN`.

### Developer Portal Setup (Phase 2)

If credentials aren't already configured, the wizard walks you through:

1. Creating a Tesla Developer account at [developer.tesla.com](https://developer.tesla.com)
2. Creating an application with the correct redirect URI (`http://localhost:8085/callback`)
3. Setting the **Allowed Origin URL** to match your domain from Phase 1
4. Entering your **Client ID** and **Client Secret**

Credentials are stored in `~/.config/tescmd/.env` as `TESLA_CLIENT_ID` and `TESLA_CLIENT_SECRET`.

### Key Generation & Deployment (Phase 3 — full tier only)

For full-control access, the wizard:

1. Generates an EC P-256 key pair (stored in `~/.config/tescmd/keys/`)
2. Deploys the public key to your GitHub Pages domain at the Tesla-required `.well-known` path
3. Waits for GitHub Pages to publish and verifies the key is accessible

If the key is already generated or deployed, these steps are skipped.

### Fleet API Registration (Phase 4)

Registers your application with Tesla's Fleet API for your region. This is a one-time requirement. The wizard:

1. Pre-checks that your public key is accessible (required by Tesla)
2. If the key isn't live, offers to generate and deploy it automatically
3. Calls the partner registration endpoint
4. On failure, provides specific remediation steps:
   - **HTTP 412 (origin mismatch):** Instructions to fix the Allowed Origin URL in the Developer Portal
   - **HTTP 424 (key not found):** Steps to generate, deploy, and validate the public key

### OAuth Login (Phase 5)

Opens your browser for Tesla OAuth2 authentication using PKCE. The wizard:

1. Starts a local callback server on port 8085
2. Opens the Tesla authorization page
3. Waits for you to sign in and grant permissions
4. Stores tokens securely in the OS keyring

If you're already logged in, this step is skipped.

### Next Steps (Phase 6)

After setup completes, the wizard prints suggested commands to try:

```
tescmd vehicle list      — list your vehicles
tescmd vehicle data      — view detailed vehicle data
tescmd vehicle location  — view vehicle location
```

For full-tier users, it also reminds you to approve the key enrollment in the Tesla app (Security → Third-Party Access).

### Re-running Setup

`tescmd setup` is safe to re-run. Each phase checks for existing configuration and skips completed steps. You can re-run it to:

- Upgrade from read-only to full control
- Re-register after changing your domain
- Complete steps that failed on a previous run

---

## `auth` — Authentication

Manage OAuth2 authentication lifecycle.

### `auth login`

Start the OAuth2 PKCE flow. Opens a browser for Tesla login.

```bash
tescmd auth login
tescmd auth login --port 9090       # custom callback port
```

### `auth logout`

Remove stored tokens from the keyring.

```bash
tescmd auth logout
tescmd auth logout --profile work   # logout specific profile
```

### `auth status`

Display current authentication state.

```bash
tescmd auth status
```

Output includes: token expiry, scopes, region, refresh token availability.

### `auth refresh`

Manually refresh the access token.

```bash
tescmd auth refresh
```

### `auth register`

Register your application with the Tesla Fleet API for a given region. This is a one-time step after creating your developer application.

```bash
tescmd auth register
```

---

## `vehicle` — Vehicle Information

Query vehicle data and manage vehicle state.

### `vehicle list`

List all vehicles on the account.

```bash
tescmd vehicle list
```

Returns: VIN, display name, state (online/asleep/offline), vehicle ID.

### `vehicle info [VIN]`

Get summary information for a vehicle.

```bash
tescmd vehicle info
tescmd vehicle info 5YJ3E1EA1NF000000
```

### `vehicle data [VIN]`

Retrieve full vehicle data snapshot. Returns all state categories at once.

```bash
tescmd vehicle data
tescmd vehicle data --endpoints charge_state,climate_state
```

**`--endpoints`** filter to specific data categories:
- `charge_state` — battery level/range (rated, ideal, estimated, usable), charge rate, voltage, current, charger power/type, energy added, cable type, port latch/door, scheduled charging, battery heater, preconditioning
- `climate_state` — interior/exterior temp, HVAC status, fan speed, defrost, front+rear seat heaters, steering wheel heater, cabin overheat protection, bioweapon defense mode, auto conditioning, preconditioning
- `drive_state` — GPS coordinates, heading, speed, shift state, power
- `vehicle_state` — locked/unlocked, doors (4), windows (4), frunk/trunk, odometer, firmware version, sentry mode, dashcam state, center display, remote start, user present, homelink nearby, TPMS tire pressure (4 wheels)
- `vehicle_config` — model, trim, color, wheels, roof color, navigation capability, trunk actuation, seat cooling, motorized charge port, power liftgate, EU vehicle
- `gui_settings` — distance units, temperature units, charge rate units

**Rich output display units:** Values are displayed in US units by default (°F, miles, PSI). The display layer converts from the API's native Celsius, miles, and bar.

### `vehicle location [VIN]`

Get the vehicle's current GPS location.

```bash
tescmd vehicle location
```

Returns: latitude, longitude, heading, speed, power.

### `vehicle wake [VIN]`

Wake a sleeping vehicle. Many data queries and all commands require the vehicle to be awake.

```bash
tescmd vehicle wake
tescmd vehicle wake --wait          # block until vehicle is online
tescmd vehicle wake --timeout 30    # wait up to 30 seconds
```

---

## `key` — Key Management

Manage EC key pairs for vehicle command signing.

### `key generate`

Generate a new EC P-256 key pair.

```bash
tescmd key generate
tescmd key generate --output ~/my-keys/  # custom output directory
```

### `key register [VIN]`

Enroll the public key on a vehicle.

```bash
tescmd key register --portal       # via Tesla Developer Portal (recommended)
tescmd key register --ble          # BLE enrollment (proximity required, alternative)
```

### `key list`

List generated keys and their enrollment status.

```bash
tescmd key list
```

---

## Roadmap — Planned Command Groups

The following command groups are planned but not yet implemented:

| Group | Description |
|---|---|
| `charge` | Charge queries and control (start, stop, limit, port, schedule) |
| `climate` | Climate control (on, off, set temp, precondition, defrost, seat heaters, bioweapon) |
| `security` | Lock, unlock, remote-start, speed-limit, valet, sentry |
| `media` | Media playback (play, pause, next, prev, volume) |
| `nav` | Navigation destinations (address, waypoint, supercharger, home, work) |
| `trunk` | Trunk and frunk control (open, close) |
| `software` | Software update queries and management |
| `fleet` | Fleet-wide operations and telemetry |
| `raw` | Arbitrary Fleet API endpoint access (get, post) |
