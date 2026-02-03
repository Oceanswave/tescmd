# Command Reference

Reference for all currently implemented tescmd commands. Commands fall into two categories:

- **Queries** — read vehicle state (location, battery, temperature, etc.). Require OAuth token only.
- **Actions** — send commands to the vehicle (charge, climate, security, trunk, media, nav, software, wake, key enrollment). Require OAuth token and may require enrolled EC key for signed commands.

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

For full-tier users, it also reminds you to approve the key enrollment in the Tesla app (Profile > Security & Privacy > Third-Party Apps).

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
tescmd auth login --reconsent       # force re-consent for expanded scopes
```

The `--reconsent` flag is needed when your application adds new OAuth scopes after initial login. Tesla caches the original consent, so without this flag, new scopes won't be granted.

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

### `auth export`

Export current tokens as JSON for transfer to another machine.

```bash
tescmd auth export > tokens.json
```

### `auth import`

Import tokens from a previously exported JSON file.

```bash
tescmd auth import < tokens.json
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

### `vehicle low-power [VIN]`

Enable or disable low power mode.

```bash
tescmd vehicle low-power --on
tescmd vehicle low-power --off
```

### `vehicle accessory-power [VIN]`

Keep accessory power (USB/outlets) active after exiting the vehicle.

```bash
tescmd vehicle accessory-power --on
tescmd vehicle accessory-power --off
```

### `vehicle telemetry config [VIN]`

Show the current Fleet Telemetry configuration for a vehicle.

```bash
tescmd vehicle telemetry config
```

### `vehicle telemetry create [VIN]`

Create a Fleet Telemetry configuration for a vehicle.

```bash
tescmd vehicle telemetry create --hostname myserver.example.com
```

### `vehicle telemetry delete [VIN]`

Delete the Fleet Telemetry configuration for a vehicle.

```bash
tescmd vehicle telemetry delete
```

### `vehicle telemetry errors [VIN]`

Show Fleet Telemetry error log for a vehicle.

```bash
tescmd vehicle telemetry errors
```

### `vehicle telemetry stream [VIN]`

Start a local WebSocket server, expose it via Tailscale Funnel, configure the vehicle to push real-time telemetry, and display an interactive dashboard.

```bash
# Rich Live dashboard (default in TTY)
tescmd vehicle telemetry stream

# Select a field preset
tescmd vehicle telemetry stream --fields driving     # Speed, location, power
tescmd vehicle telemetry stream --fields charging    # Battery, voltage, current
tescmd vehicle telemetry stream --fields climate     # Temps, HVAC state
tescmd vehicle telemetry stream --fields all         # All 120+ fields

# Override polling interval for all fields
tescmd vehicle telemetry stream --interval 5

# JSONL output for scripting/agents
tescmd vehicle telemetry stream --format json
```

**Options:**
- `--fields PRESET` — Field preset name (`default`, `driving`, `charging`, `climate`, `all`) or comma-separated field names
- `--interval SECONDS` — Override polling interval for all fields
- `--format json` — Emit one JSON line per telemetry frame instead of Rich dashboard

**Requires:** Tailscale with Funnel enabled.

Press `q` to stop. Cleanup is automatic (removes telemetry config, restores partner domain, stops tunnel).

---

## `key` — Key Management

Manage EC key pairs for vehicle command signing.

### `key generate`

Generate a new EC P-256 key pair.

```bash
tescmd key generate
tescmd key generate --force  # overwrite existing keys
```

### `key enroll`

Opens the Tesla enrollment URL so you can add your virtual key via the Tesla app.

```bash
tescmd key enroll            # open enrollment URL in browser
tescmd key enroll --no-open  # print URL without opening browser
```

**Rich mode (TTY):** Validates that keys exist, domain is configured, and the public key is accessible, then displays the enrollment URL with step-by-step instructions:

```
ACTION REQUIRED: Add virtual key in the Tesla app

  Enrollment URL: https://tesla.com/_ak/yourdomain.github.io

  1. Scan the QR code on the page above with your phone
  2. The Tesla app will show an Add Virtual Key prompt
  3. Approve it

```

**JSON mode:** Returns a single envelope with `"status": "ready"`, `enroll_url`, and instructions.

### `key deploy`

Deploy the public key to a hosting service (at the `.well-known` path Tesla requires). Auto-detects the best method: GitHub Pages → Tailscale Funnel → manual.

```bash
tescmd key deploy                              # auto-detect best method
tescmd key deploy --method github              # force GitHub Pages
tescmd key deploy --method tailscale           # force Tailscale Funnel
tescmd key deploy --repo user/user.github.io   # explicit GitHub repo
```

The `--method` flag overrides auto-detection. The choice is persisted in `TESLA_HOSTING_METHOD`.

### `key validate`

Check that the public key is accessible at the expected URL.

```bash
tescmd key validate
```

### `key show`

Display key path, fingerprint, and expected URL.

```bash
tescmd key show
```

### `key unenroll [VIN]`

Remove your enrolled key from a vehicle.

```bash
tescmd key unenroll
tescmd key unenroll 5YJ3E1EA1NF000000
```

---

## `charge` — Charging Control

Manage charging state, limits, current, schedules, and charge port.

### `charge status [VIN]`

Show current charging status (battery level, range, charge rate, port state).

```bash
tescmd charge status
```

### `charge start [VIN]`

Start charging.

```bash
tescmd charge start
```

### `charge stop [VIN]`

Stop charging.

```bash
tescmd charge stop
```

### `charge limit [VIN] PERCENT`

Set charge limit to a specific percentage (50-100).

```bash
tescmd charge limit 80
```

### `charge limit-max [VIN]`

Set charge limit to maximum range.

```bash
tescmd charge limit-max
```

### `charge limit-std [VIN]`

Set charge limit to standard range.

```bash
tescmd charge limit-std
```

### `charge amps [VIN] AMPS`

Set charging current (0-48 amps).

```bash
tescmd charge amps 32
```

### `charge port-open [VIN]`

Open the charge port door.

```bash
tescmd charge port-open
```

### `charge port-close [VIN]`

Close the charge port door.

```bash
tescmd charge port-close
```

### `charge schedule [VIN]`

Configure scheduled charging.

```bash
tescmd charge schedule --time 420          # 7:00 AM (minutes past midnight)
tescmd charge schedule --disable           # disable scheduled charging
```

### `charge departure [VIN]`

Configure scheduled departure with preconditioning and off-peak charging.

```bash
tescmd charge departure --time 480         # depart at 8:00 AM
tescmd charge departure --time 480 --precondition --off-peak
tescmd charge departure --off              # disable
```

### `charge add-schedule [VIN]`

Add or update a charge schedule (firmware 2024.26+).

```bash
tescmd charge add-schedule --id 1 --name "Weeknights" --start-time 1380 --end-time 420
```

### `charge remove-schedule [VIN]`

Remove a charge schedule by ID.

```bash
tescmd charge remove-schedule --id 1
```

### `charge managed-amps [VIN] AMPS`

Set managed charging current in amps (fleet management). Used by fleet operators to control charging across multiple vehicles.

```bash
tescmd charge managed-amps 16
tescmd charge managed-amps 24
```

---

## `climate` — Climate and Comfort

Control HVAC, seat heaters, steering wheel heater, and cabin overheat protection.

### `climate status [VIN]`

Show current climate state (temperatures, HVAC, seat heaters, fan speed).

```bash
tescmd climate status
```

### `climate on [VIN]`

Turn climate control on.

```bash
tescmd climate on
```

### `climate off [VIN]`

Turn climate control off.

```bash
tescmd climate off
```

### `climate set [VIN] TEMP`

Set cabin temperature (in Fahrenheit or Celsius depending on vehicle settings).

```bash
tescmd climate set 72
```

### `climate seat [VIN] POSITION LEVEL`

Set seat heater level for a specific seat.

```bash
tescmd climate seat driver 2              # driver seat, level 2 (0-3)
tescmd climate seat passenger 0           # passenger seat off
tescmd climate seat rear-left 1           # rear left
```

Positions: `driver`, `passenger`, `rear-left`, `rear-center`, `rear-right`, `third-left`, `third-right`

### `climate wheel-heater [VIN]`

Control the steering wheel heater.

```bash
tescmd climate wheel-heater --on
tescmd climate wheel-heater --off
```

### `climate keeper [VIN]`

Set cabin overheat protection (Keep Climate, Dog Mode, Camp Mode).

```bash
tescmd climate keeper --on --mode keep     # keep climate
tescmd climate keeper --on --mode dog      # dog mode
tescmd climate keeper --on --mode camp     # camp mode
tescmd climate keeper --off                # disable
```

### `climate cop-temp [VIN]`

Set cabin overheat protection temperature.

```bash
tescmd climate cop-temp 90                 # 90°F
```

### `climate bioweapon [VIN]`

Control Bioweapon Defense Mode.

```bash
tescmd climate bioweapon --on
tescmd climate bioweapon --off
tescmd climate bioweapon --on --manual-override  # force manual override
```

**`--manual-override`** — Force manual override of automatic behavior.

### `climate defrost [VIN]`

Control preconditioning/defrost.

```bash
tescmd climate defrost --on
tescmd climate defrost --off
```

---

## `security` — Security and Access

Lock/unlock doors, sentry mode, valet mode, speed limits, and more.

### `security status [VIN]`

Show current security status (locks, sentry, doors, windows).

```bash
tescmd security status
```

### `security lock [VIN]`

Lock all doors.

```bash
tescmd security lock
```

### `security unlock [VIN]`

Unlock all doors.

```bash
tescmd security unlock
```

### `security flash [VIN]`

Flash the vehicle lights.

```bash
tescmd security flash
```

### `security honk [VIN]`

Honk the horn.

```bash
tescmd security honk
```

### `security sentry [VIN]`

Enable or disable sentry mode.

```bash
tescmd security sentry --on
tescmd security sentry --off
```

### `security valet [VIN]`

Enable or disable valet mode.

```bash
tescmd security valet --on
tescmd security valet --on --password 1234
tescmd security valet --off
```

### `security remote-start [VIN]`

Enable remote start.

```bash
tescmd security remote-start
```

### `security speed-limit [VIN]`

Manage speed limit mode.

```bash
tescmd security speed-limit --set 65       # set to 65 MPH
tescmd security speed-limit --set 65.5     # fractional MPH accepted
tescmd security speed-limit --activate 1234  # activate with PIN
tescmd security speed-limit --deactivate 1234
```

### `security pin-to-drive [VIN]`

Enable or disable PIN to Drive.

```bash
tescmd security pin-to-drive --on --password 1234
tescmd security pin-to-drive --off
```

### `security guest-mode [VIN]`

Enable or disable guest mode.

```bash
tescmd security guest-mode --on
tescmd security guest-mode --off
```

### `security erase-data [VIN]`

Erase all user data from the vehicle. Requires `--confirm` flag.

```bash
tescmd security erase-data --confirm
```

### `security boombox [VIN]`

Activate the boombox (external speaker).

```bash
tescmd security boombox                    # default: locate sound (ping)
tescmd security boombox --sound locate     # locate sound (ping)
tescmd security boombox --sound fart       # fart sound
```

**`--sound`** — Sound to play: `locate` (default, ping/chirp) or `fart`.

---

## `trunk` — Trunk and Window Control

Operate trunks, frunk, sunroof, and windows.

### `trunk open [VIN]`

Open (toggle) the rear trunk.

```bash
tescmd trunk open
```

### `trunk close [VIN]`

Close (toggle) the rear trunk.

```bash
tescmd trunk close
```

### `trunk frunk [VIN]`

Open the front trunk (frunk).

```bash
tescmd trunk frunk
```

### `trunk sunroof [VIN]`

Control the panoramic sunroof.

```bash
tescmd trunk sunroof --state vent          # vent the sunroof
tescmd trunk sunroof --state close         # close the sunroof
tescmd trunk sunroof --state stop          # stop sunroof movement
```

**`--state`** (required) — Action: `vent`, `close`, or `stop`.

### `trunk tonneau-open [VIN]`

Open the Cybertruck tonneau cover.

```bash
tescmd trunk tonneau-open
```

### `trunk tonneau-close [VIN]`

Close the Cybertruck tonneau cover.

```bash
tescmd trunk tonneau-close
```

### `trunk tonneau-stop [VIN]`

Stop the Cybertruck tonneau cover movement.

```bash
tescmd trunk tonneau-stop
```

### `trunk window [VIN]`

Vent or close all windows. Closing requires vehicle coordinates (auto-detected if not provided).

```bash
tescmd trunk window --vent
tescmd trunk window --close
tescmd trunk window --close --lat 37.38 --lon -122.08
```

---

## `media` — Media Playback

Control media playback and volume.

### `media play-pause [VIN]`

Toggle media playback (play/pause).

```bash
tescmd media play-pause
```

### `media next-track [VIN]`

Skip to the next track.

```bash
tescmd media next-track
```

### `media prev-track [VIN]`

Skip to the previous track.

```bash
tescmd media prev-track
```

### `media next-fav [VIN]`

Skip to the next favorite.

```bash
tescmd media next-fav
```

### `media prev-fav [VIN]`

Skip to the previous favorite.

```bash
tescmd media prev-fav
```

### `media volume-up [VIN]`

Increase volume by one step.

```bash
tescmd media volume-up
```

### `media volume-down [VIN]`

Decrease volume by one step.

```bash
tescmd media volume-down
```

### `media adjust-volume [VIN] VOLUME`

Set volume to a specific level (0.0–11.0). Accepts fractional values for fine-grained control.

```bash
tescmd media adjust-volume 5
tescmd media adjust-volume 7.5
```

---

## `nav` — Navigation

Send destinations, coordinates, and trigger HomeLink.

### `nav send [VIN] ADDRESS`

Send an address to the vehicle navigation.

```bash
tescmd nav send "1 Infinite Loop, Cupertino, CA"
```

### `nav gps [VIN] COORDS...`

Navigate to GPS coordinates. Accepts `LAT LON` pairs or comma-separated `LAT,LON` strings.

```bash
# Single destination
tescmd nav gps 37.3861 -122.0839

# Comma-separated format
tescmd nav gps 37.3861,-122.0839

# With explicit waypoint order
tescmd nav gps 37.3861 -122.0839 --order 1

# Multi-stop route (auto-ordered)
tescmd nav gps 37.3861,-122.0839 37.3382,-121.8863
```

### `nav supercharger [VIN]`

Navigate to the nearest Supercharger.

```bash
tescmd nav supercharger
```

### `nav homelink [VIN]`

Trigger HomeLink (garage door). Auto-detects vehicle location unless `--lat`/`--lon` provided.

```bash
tescmd nav homelink
tescmd nav homelink --lat 37.38 --lon -122.08
```

### `nav waypoints [VIN] PLACE_IDS...`

Send multi-stop waypoints using Google Maps Place IDs. Each ID is automatically prefixed with `refId:` and joined into a comma-separated string.

```bash
tescmd nav waypoints ChIJIQBpAG2ahYAR_6128GcTUEo ChIJw____96GhYARCVVwg5cT7c0
```

---

## `software` — Software Updates

Check and manage software updates.

### `software status [VIN]`

Show current firmware version and update status.

```bash
tescmd software status
```

### `software schedule [VIN] SECONDS`

Schedule a pending software update to install in SECONDS from now.

```bash
tescmd software schedule 7200             # install in 2 hours
```

### `software cancel [VIN]`

Cancel a scheduled software update.

```bash
tescmd software cancel
```

---

## `energy` — Energy Products

Manage Tesla energy products (Powerwall, Solar, etc.).

### `energy list`

List all energy products on the account.

```bash
tescmd energy list
```

### `energy status SITE_ID`

Show energy site status and configuration.

```bash
tescmd energy status 12345
```

### `energy live SITE_ID`

Show real-time energy site data (solar production, battery level, grid usage).

```bash
tescmd energy live 12345
```

### `energy backup SITE_ID PERCENT`

Set backup reserve percentage (0-100).

```bash
tescmd energy backup 12345 20
```

### `energy mode SITE_ID MODE`

Set the operation mode.

```bash
tescmd energy mode 12345 self_consumption
tescmd energy mode 12345 autonomous
```

### `energy storm SITE_ID`

Enable or disable Storm Watch mode.

```bash
tescmd energy storm 12345 --on
tescmd energy storm 12345 --off
```

### `energy tou SITE_ID`

Configure time-of-use schedule.

```bash
tescmd energy tou 12345 --schedule '{"tou_settings": {...}}'
```

### `energy history SITE_ID`

View energy charging history.

```bash
tescmd energy history 12345
```

### `energy off-grid SITE_ID`

Enable or disable off-grid vehicle charging.

```bash
tescmd energy off-grid 12345 --on
tescmd energy off-grid 12345 --off
```

### `energy grid-config SITE_ID`

Manage grid import/export configuration.

```bash
tescmd energy grid-config 12345
```

### `energy calendar SITE_ID`

View calendar-based energy history.

```bash
tescmd energy calendar 12345
tescmd energy calendar 12345 --kind power --period month
```

---

## `user` — User Account

Query user account information.

### `user me`

Display current user account details.

```bash
tescmd user me
```

### `user region`

Show the user's assigned API region.

```bash
tescmd user region
```

### `user orders`

List vehicle orders on the account.

```bash
tescmd user orders
```

### `user features`

Show available feature flags for the account.

```bash
tescmd user features
```

---

## `sharing` — Vehicle Sharing

Manage vehicle sharing and driver invitations.

### `sharing add-driver [VIN]`

Add a driver to a vehicle.

```bash
tescmd sharing add-driver --email driver@example.com
```

### `sharing remove-driver [VIN]`

Remove a driver from a vehicle.

```bash
tescmd sharing remove-driver --share-user-id USER_ID
```

### `sharing create-invite [VIN]`

Create a vehicle sharing invitation.

```bash
tescmd sharing create-invite
```

### `sharing redeem-invite`

Redeem a vehicle sharing invitation code.

```bash
tescmd sharing redeem-invite --code INVITE_CODE
```

### `sharing revoke-invite [VIN]`

Revoke an existing sharing invitation.

```bash
tescmd sharing revoke-invite --invite-id INVITE_ID
```

### `sharing list-invites [VIN]`

List all active sharing invitations.

```bash
tescmd sharing list-invites
```

---

## `openclaw` — OpenClaw Integration

Stream filtered vehicle telemetry to an OpenClaw Gateway for real-time agent consumption.

### `openclaw bridge [VIN]`

Start a long-running bridge that streams Fleet Telemetry through a dual-gate filter (delta threshold + throttle interval) to an OpenClaw Gateway.

```bash
# Connect to a local OpenClaw Gateway
tescmd openclaw bridge

# Specify gateway URL and auth token
tescmd openclaw bridge --gateway ws://gateway.example.com:18789 --token SECRET

# Use a config file for filter settings
tescmd openclaw bridge --config ~/.config/tescmd/bridge.json

# Dry-run mode (print JSONL to stdout, no gateway connection)
tescmd openclaw bridge --dry-run

# Override field polling interval
tescmd openclaw bridge --interval 10

# Select specific field presets
tescmd openclaw bridge --fields driving

```

**Options:**
- `--gateway URL` — Gateway WebSocket URL (default: `ws://127.0.0.1:18789`, env: `OPENCLAW_GATEWAY_URL`)
- `--token TOKEN` — Gateway authentication token (env: `OPENCLAW_GATEWAY_TOKEN`)
- `--config PATH` — Bridge config JSON file with per-field filter settings
- `--port PORT` — Local WebSocket server port for telemetry
- `--fields PRESET` — Field preset (`default`, `driving`, `charging`, `climate`, `all`) or comma-separated names
- `--interval SECONDS` — Override polling interval for all fields
- `--dry-run` — Print filtered events as JSONL without connecting to gateway

**Requires:** Tailscale with Funnel enabled.

The bridge uses dual-gate filtering: each field must exceed both a delta threshold (value change) AND a throttle interval (minimum time between emissions) before being forwarded to the gateway. Default thresholds: location 50m/1s, battery 5%/10s, temperature 5deg/30s, speed 5mph/2s, state changes emit immediately.

---

## `serve` — Unified Server

The recommended way to run tescmd as a server. Combines MCP, telemetry cache warming, Rich TUI dashboard, and OpenClaw bridging into a single command. Auto-detects TTY for dashboard vs JSONL output.

```bash
# MCP + telemetry cache warming (recommended for agents)
tescmd serve 5YJ3...

# MCP only (no telemetry)
tescmd serve --no-telemetry

# Telemetry dashboard only (no MCP)
tescmd serve 5YJ3... --no-mcp

# MCP + cache warming + OpenClaw bridge
tescmd serve 5YJ3... --openclaw ws://gw.example.com:18789

# stdio transport for Claude Desktop / Claude Code
tescmd serve --transport stdio

# OpenClaw dry-run: log events as JSONL without sending
tescmd serve 5YJ3... --openclaw ws://gw.example.com:18789 --dry-run

# Custom OpenClaw config file
tescmd serve 5YJ3... --openclaw ws://gw.example.com:18789 --openclaw-config bridge.json
```

**Options:**

| Option | Description | Default |
|---|---|---|
| `VIN` | Vehicle identification number (positional) | Profile default |
| `--transport` | `streamable-http` or `stdio` | `streamable-http` |
| `--port PORT` | MCP HTTP port (streamable-http only) | `8080` |
| `--telemetry-port PORT` | WebSocket port for telemetry | Random ephemeral |
| `--fields PRESET` | Field preset or comma-separated names | `default` |
| `--interval SECONDS` | Override telemetry interval for all fields | Per-field defaults |
| `--no-telemetry` | MCP-only mode — skip telemetry and cache warming | Off |
| `--no-mcp` | Telemetry-only mode — skip MCP server | Off |
| `--openclaw URL` | Bridge telemetry to an OpenClaw gateway | Off |
| `--openclaw-token TOKEN` | OpenClaw gateway auth token (env: `OPENCLAW_GATEWAY_TOKEN`) | None |
| `--openclaw-config PATH` | OpenClaw bridge config file (JSON) | Default config |
| `--dry-run` | OpenClaw dry-run: log events as JSONL | Off |
| `--tailscale` | Expose MCP via Tailscale Funnel | Off |
| `--client-id ID` | MCP client ID (env: `TESCMD_MCP_CLIENT_ID`) | Required (unless `--no-mcp`) |
| `--client-secret SECRET` | MCP client secret (env: `TESCMD_MCP_CLIENT_SECRET`) | Required (unless `--no-mcp`) |

### Mode Matrix

| Invocation | MCP | Telemetry | Dashboard | Cache | OpenClaw |
|---|---|---|---|---|---|
| `serve VIN` (TTY) | HTTP | yes | Rich TUI | yes | - |
| `serve VIN` (piped) | HTTP | yes | - | yes | - |
| `serve --no-telemetry` | HTTP | - | - | - | - |
| `serve --transport stdio` | stdio | - | - | - | - |
| `serve VIN --openclaw ws://..` | HTTP | yes | auto | yes | yes |
| `serve VIN --no-mcp` (TTY) | - | yes | Rich TUI | - | - |
| `serve VIN --no-mcp --format json` | - | yes | JSONL stdout | - | - |

### When to Use Which

| Need | Command |
|---|---|
| Production agent setup | `tescmd serve VIN` |
| Claude Desktop / Claude Code | `tescmd serve --transport stdio` |
| Quick MCP test without telemetry | `tescmd serve --no-telemetry` |
| Watch live telemetry dashboard | `tescmd serve VIN --no-mcp` |
| Agent + OpenClaw in one process | `tescmd serve VIN --openclaw ws://...` |
| Standalone OpenClaw bridge | `tescmd openclaw bridge` |
| Interactive telemetry with q-to-quit | `tescmd vehicle telemetry stream` |

### Configuration

The `serve` command reads `.env` files automatically via `python-dotenv`. The resolution order:

1. `.env` in the current working directory
2. `~/.config/tescmd/.env` (created by `tescmd setup`)
3. Environment variables set in the shell

See `.env.example` in the repository root for a template with all supported variables.

---

## `mcp` — MCP Server

Expose tescmd commands as MCP (Model Context Protocol) tools for AI agent frameworks.

### `mcp serve`

Start an MCP server that registers all tescmd read and write commands as tools. Each tool invokes the corresponding CLI command via Click's CliRunner, guaranteeing behavioral parity with the CLI (caching, wake, auth, error handling all work).

```bash
# Start HTTP server on port 8080 (default)
tescmd mcp serve

# Start stdio transport (for Claude Desktop, Claude Code)
tescmd mcp serve --transport stdio

# Start on a custom port
tescmd mcp serve --port 9090

# Expose publicly via Tailscale Funnel
tescmd mcp serve --tailscale
```

**Options:**
- `--transport {stdio,streamable-http}` — MCP transport type (default: `streamable-http`)
- `--port PORT` — HTTP port for streamable-http transport (default: `8080`)
- `--tailscale` — Expose via Tailscale Funnel (cannot combine with `--transport stdio`)
- `--client-id ID` — MCP client ID (env: `TESCMD_MCP_CLIENT_ID`, required)
- `--client-secret SECRET` — MCP client secret / bearer token (env: `TESCMD_MCP_CLIENT_SECRET`, required)

**Authentication:** All transports require `TESCMD_MCP_CLIENT_ID` and `TESCMD_MCP_CLIENT_SECRET`. The HTTP transport implements the full MCP OAuth 2.1 specification — clients authenticate via an authorization code flow with PKCE (the server auto-approves). MCP clients like Claude.ai and Claude Code handle this flow automatically. The stdio transport requires credentials for consistency but does not validate on the wire.

**Requires:** Included in standard install. `--tailscale` requires Tailscale with Funnel enabled.

**Claude Code configuration** (`.mcp.json`):
```json
{
  "mcpServers": {
    "tescmd": {
      "command": "tescmd",
      "args": ["mcp", "serve", "--transport", "stdio"],
      "env": {
        "TESCMD_MCP_CLIENT_ID": "claude-code",
        "TESCMD_MCP_CLIENT_SECRET": "your-secret-here"
      }
    }
  }
}
```

All read tools are annotated with `readOnlyHint: true`; write tools with `readOnlyHint: false`. Long-running and interactive commands (telemetry stream, openclaw bridge, auth login, setup) are excluded from the MCP server.

---

## `cache` — Response Cache

Manage the local response cache.

### `cache status`

Show cache statistics (entry count, disk usage, hit rate).

```bash
tescmd cache status
```

### `cache clear`

Clear cached responses.

```bash
tescmd cache clear               # clear all entries
tescmd cache clear --vin VIN     # clear for a specific vehicle
```

---

## `raw` — Arbitrary API Access

Access any Fleet API endpoint directly. Use this for endpoints not yet covered by a dedicated command.

### `raw get PATH`

Make a GET request to any Fleet API path.

```bash
tescmd raw get /api/1/vehicles
tescmd raw get "/api/1/vehicles/{VIN}/vehicle_data"
```

### `raw post PATH`

Make a POST request to any Fleet API path with an optional JSON body.

```bash
tescmd raw post "/api/1/vehicles/{VIN}/command/flash_lights"
tescmd raw post "/api/1/vehicles/{VIN}/command/set_temps" --body '{"driver_temp": 22}'
```

---

## `billing` — Supercharger Billing

View Supercharger charging history, sessions, and invoices.

### `billing history`

Show Supercharger charging history with optional filters.

```bash
tescmd billing history
tescmd billing history --vin 5YJ3E1EA1NF000000
tescmd billing history --start 2025-01-01T00:00:00Z --end 2025-02-01T00:00:00Z
tescmd billing history --page 0 --page-size 50
```

**Options:**
- `--vin VIN` — Filter by vehicle VIN
- `--start` / `--end` — Date range (ISO-8601)
- `--page` / `--page-size` — Pagination

### `billing sessions`

Show charging sessions (business/fleet accounts).

```bash
tescmd billing sessions
tescmd billing sessions --vin VIN --from 2025-01-01T00:00:00Z --limit 25
```

### `billing invoice INVOICE_ID`

Download a charging invoice by ID.

```bash
tescmd billing invoice INV-123456
tescmd billing invoice INV-123456 -o invoice.pdf
```

---

## `partner` — Partner Account

Partner-level endpoints for managing Fleet API registration and telemetry diagnostics. Requires client credentials.

### `partner public-key`

Look up the public key registered for a domain.

```bash
tescmd partner public-key --domain yourdomain.github.io
```

### `partner telemetry-error-vins`

List VINs with recent fleet telemetry errors.

```bash
tescmd partner telemetry-error-vins
```

### `partner telemetry-errors`

Get recent fleet telemetry errors across all vehicles.

```bash
tescmd partner telemetry-errors
```

---

## `status` — Configuration Overview

Single-command overview of current configuration, authentication, and cache state.

```bash
tescmd status
```

Displays: active profile, region, VIN, setup tier, domain, client ID, auth state (token expiry, refresh availability), cache statistics (entries, fresh/stale), config/cache directory paths, key pairs, and token backend.

---

## API-Only Endpoints

The following endpoints are implemented in the API layer but not yet exposed as dedicated CLI commands. They can be accessed via `tescmd raw get` or `tescmd raw post`.

### Vehicle Endpoints

| Endpoint | API Method | Description |
|----------|-----------|-------------|
| `GET /dx/vehicles/subscriptions/eligibility` | `VehicleAPI.eligible_subscriptions()` | Check subscription eligibility |
| `GET /dx/vehicles/upgrades/eligibility` | `VehicleAPI.eligible_upgrades()` | Check upgrade eligibility |
| `GET /dx/vehicles/options` | `VehicleAPI.options()` | Get vehicle options |
| `GET /vehicles/{vin}/specs` | `VehicleAPI.specs()` | Get vehicle specifications |
| `GET /dx/warranty/details` | `VehicleAPI.warranty_details()` | Get warranty details |
| `POST /vehicles/fleet_status` | `VehicleAPI.fleet_status()` | Get fleet status |
| `GET /vehicles/{vin}/fleet_telemetry_config` | `VehicleAPI.fleet_telemetry_config()` | Get Fleet Telemetry config |
| `GET /vehicles/{vin}/fleet_telemetry_errors` | `VehicleAPI.fleet_telemetry_errors()` | Get Fleet Telemetry errors |

### Energy Endpoints

| Endpoint | API Method | Description |
|----------|-----------|-------------|
| `GET /energy_sites/{id}/telemetry_history` | `EnergyAPI.telemetry_history()` | Telemetry-based charge history |

### Vehicle Commands (Fleet Management)

| Command | API Method | Description |
|---------|-----------|-------------|
| `navigation_request` | `CommandAPI.navigation_request()` | Legacy navigation (REST-only, share endpoint preferred) |
| `set_managed_charger_location` | `CommandAPI.set_managed_charger_location()` | Set managed charger location (fleet) |
| `set_managed_scheduled_charging_time` | `CommandAPI.set_managed_scheduled_charging_time()` | Set managed scheduled charging time (fleet) |
