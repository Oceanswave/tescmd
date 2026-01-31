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

  1. Open the URL above on your phone
  2. Tap Finish Setup on the web page
  3. The Tesla app will show an Add Virtual Key prompt
  4. Approve it
```

**JSON mode:** Returns a single envelope with `"status": "ready"`, `enroll_url`, and instructions.

### `key deploy`

Deploy the public key to GitHub Pages (at the `.well-known` path Tesla requires).

```bash
tescmd key deploy
tescmd key deploy --repo user/user.github.io  # explicit repo
```

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
```

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
tescmd security boombox
```

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

Vent or close the panoramic sunroof.

```bash
tescmd trunk sunroof --vent
tescmd trunk sunroof --close
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

Set volume to a specific level (0-11).

```bash
tescmd media adjust-volume 5
```

---

## `nav` — Navigation

Send destinations, coordinates, and trigger HomeLink.

### `nav send [VIN] ADDRESS`

Send an address to the vehicle navigation.

```bash
tescmd nav send "1 Infinite Loop, Cupertino, CA"
```

### `nav gps [VIN] LAT LON`

Navigate to GPS coordinates.

```bash
tescmd nav gps 37.3861 -122.0839
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

### `nav waypoints [VIN] WAYPOINTS_JSON`

Send multi-stop waypoints as a JSON array.

```bash
tescmd nav waypoints '[{"lat": 37.38, "lon": -122.08}, {"lat": 37.40, "lon": -122.10}]'
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
