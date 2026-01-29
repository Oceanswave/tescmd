# Command Reference

Complete reference for all tescmd commands. Commands fall into two categories:

- **Queries** — read vehicle state (location, battery, temperature, etc.). Require OAuth token only.
- **Actions** — send commands to the vehicle (start charge, set climate, lock, etc.). Require OAuth token and may require enrolled EC key.

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
3. Profile default: `vin` field in active config profile
4. `TESLA_VIN` environment variable
5. Interactive picker: lists your vehicles and prompts you to choose

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

### `auth export`

Export tokens as JSON (for transferring to headless machines).

```bash
tescmd auth export > tokens.json
```

### `auth import`

Import tokens from JSON.

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
- `charge_state` — battery level, charge rate, limit, cable status, scheduled charging
- `climate_state` — interior/exterior temp, HVAC status, seat heaters, preconditioning
- `drive_state` — GPS coordinates, heading, speed, shift state, power
- `vehicle_state` — locked/unlocked, doors, windows, odometer, firmware version, sentry mode
- `vehicle_config` — model, trim, color, options, wheel type
- `gui_settings` — distance units, temperature units, charge rate units

### `vehicle location [VIN]`

Get the vehicle's current GPS location.

```bash
tescmd vehicle location
```

Returns: latitude, longitude, heading, timestamp. In Rich mode, displays a human-readable address if available.

### `vehicle wake [VIN]`

Wake a sleeping vehicle. Many data queries and all commands require the vehicle to be awake.

```bash
tescmd vehicle wake
tescmd vehicle wake --wait          # block until vehicle is online
tescmd vehicle wake --timeout 30    # wait up to 30 seconds
```

---

## `charge` — Charging

Query charging status and control charging.

### `charge status [VIN]`

Display current charging state.

```bash
tescmd charge status
```

Returns: battery level (%), charge rate, voltage, current, time remaining, charge limit, cable connected, charger type (AC/DC), scheduled start time.

### `charge start [VIN]`

Start charging (vehicle must be plugged in).

```bash
tescmd charge start
```

### `charge stop [VIN]`

Stop charging.

```bash
tescmd charge stop
```

### `charge limit [VIN] [PERCENT]`

Get or set the charge limit.

```bash
tescmd charge limit              # query current limit
tescmd charge limit 80           # set to 80%
tescmd charge limit --max        # set to maximum (100%)
tescmd charge limit --standard   # set to standard (~90%)
```

### `charge port-open [VIN]`

Open the charge port.

```bash
tescmd charge port-open
```

### `charge port-close [VIN]`

Close the charge port.

```bash
tescmd charge port-close
```

### `charge schedule [VIN]`

Get or set scheduled charging.

```bash
tescmd charge schedule                  # query current schedule
tescmd charge schedule --time 23:00     # set scheduled start
tescmd charge schedule --off            # disable scheduled charging
```

---

## `climate` — Climate Control

Query climate state and control HVAC.

### `climate status [VIN]`

Display current climate state.

```bash
tescmd climate status
```

Returns: interior temp, exterior temp, driver/passenger set temp, HVAC on/off, fan speed, defrost status, seat heater levels, steering wheel heater, bioweapon defense mode.

### `climate on [VIN]`

Turn on climate control (HVAC).

```bash
tescmd climate on
```

### `climate off [VIN]`

Turn off climate control.

```bash
tescmd climate off
```

### `climate set [VIN]`

Set the target temperature.

```bash
tescmd climate set --temp 72          # set driver temp (°F)
tescmd climate set --temp 22 --celsius # set driver temp (°C)
tescmd climate set --driver 70 --passenger 74   # split temps
```

### `climate precondition [VIN]`

Start preconditioning for a departure time.

```bash
tescmd climate precondition --time 07:30
tescmd climate precondition --off
```

### `climate defrost [VIN]`

Control defrost mode.

```bash
tescmd climate defrost --on
tescmd climate defrost --off
```

### `climate seat-heater [VIN]`

Control seat heaters.

```bash
tescmd climate seat-heater --seat driver --level 3
tescmd climate seat-heater --seat rear-left --level 0    # off
tescmd climate seat-heater --all --level 2
```

Seats: `driver`, `passenger`, `rear-left`, `rear-center`, `rear-right`.
Levels: `0` (off), `1` (low), `2` (medium), `3` (high).

### `climate bioweapon [VIN]`

Toggle Bioweapon Defense Mode.

```bash
tescmd climate bioweapon --on
tescmd climate bioweapon --off
```

---

## `security` — Security

Query security state and control locks, sentry, and access.

### `security status [VIN]`

Display current security state.

```bash
tescmd security status
```

Returns: locked/unlocked, doors open/closed, windows open/closed, sentry mode on/off, valet mode, speed limit.

### `security lock [VIN]`

Lock the vehicle.

```bash
tescmd security lock
```

### `security unlock [VIN]`

Unlock the vehicle.

```bash
tescmd security unlock
```

### `security remote-start [VIN]`

Enable keyless driving (2 minutes to start driving).

```bash
tescmd security remote-start
```

### `security speed-limit [VIN]`

Get or set the speed limit.

```bash
tescmd security speed-limit                     # query current limit
tescmd security speed-limit --set 75 --pin 1234 # set limit to 75 mph
tescmd security speed-limit --clear --pin 1234  # remove limit
```

### `security valet [VIN]`

Control valet mode.

```bash
tescmd security valet --on --pin 1234
tescmd security valet --off --pin 1234
```

### `security sentry [VIN]`

Control Sentry Mode.

```bash
tescmd security sentry --on
tescmd security sentry --off
tescmd security sentry status    # query sentry mode state
```

---

## `media` — Media Playback

Control the vehicle's media player.

### `media status [VIN]`

Display current media state.

```bash
tescmd media status
```

Returns: now playing (title, artist, album), source, volume, playback state.

### `media play [VIN]` / `media pause [VIN]`

```bash
tescmd media play
tescmd media pause
```

### `media toggle-playback [VIN]`

```bash
tescmd media toggle-playback
```

### `media next [VIN]` / `media prev [VIN]`

```bash
tescmd media next
tescmd media prev
```

### `media volume-up [VIN]` / `media volume-down [VIN]`

```bash
tescmd media volume-up
tescmd media volume-down
```

---

## `nav` — Navigation

Send navigation destinations to the vehicle.

### `nav set [VIN] ADDRESS`

Send an address to the vehicle's navigation.

```bash
tescmd nav set "1600 Amphitheatre Parkway, Mountain View, CA"
```

### `nav waypoint [VIN] ADDRESS`

Add a waypoint to the current route.

```bash
tescmd nav waypoint "123 Main St, Palo Alto, CA"
```

### `nav sc [VIN]`

Navigate to the nearest Supercharger.

```bash
tescmd nav sc
```

### `nav home [VIN]`

Navigate home (uses vehicle's saved home address).

```bash
tescmd nav home
```

### `nav work [VIN]`

Navigate to work (uses vehicle's saved work address).

```bash
tescmd nav work
```

---

## `trunk` — Trunk and Frunk

Control trunk and front trunk.

### `trunk open [VIN]`

Open or pop the rear trunk.

```bash
tescmd trunk open
```

### `trunk close [VIN]`

Close the rear trunk (power trunk models only).

```bash
tescmd trunk close
```

### `trunk frunk [VIN]`

Open the front trunk (frunk). Note: frunks cannot be closed remotely.

```bash
tescmd trunk frunk
```

---

## `software` — Software Updates

Query and manage vehicle software updates.

### `software status [VIN]`

Check for available software updates.

```bash
tescmd software status
```

Returns: current firmware version, update availability, download progress, scheduled install time.

### `software update [VIN]`

Start installing an available software update.

```bash
tescmd software update
tescmd software update --schedule 02:00   # schedule for 2 AM
```

### `software cancel [VIN]`

Cancel a scheduled software update.

```bash
tescmd software cancel
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

### `key delete`

Delete a local key pair.

```bash
tescmd key delete
tescmd key delete --name my-key
```

---

## `fleet` — Fleet Operations

Fleet-wide queries and management.

### `fleet status`

Display fleet-level account status.

```bash
tescmd fleet status
```

### `fleet telemetry [VIN]`

Query or configure telemetry streaming.

```bash
tescmd fleet telemetry status
tescmd fleet telemetry configure --fields speed,location,battery --interval 30
```

---

## `raw` — Raw API Access

Make arbitrary requests to the Tesla Fleet API. Useful for accessing endpoints not yet wrapped by tescmd, or for debugging.

### `raw get PATH`

```bash
tescmd raw get /api/1/vehicles
tescmd raw get /api/1/vehicles/{vin}/vehicle_data
```

### `raw post PATH`

```bash
tescmd raw post /api/1/vehicles/{vin}/command/flash_lights
tescmd raw post /api/1/vehicles/{vin}/command/set_temps --data '{"driver_temp": 22, "passenger_temp": 22}'
```

`{vin}` in the path is automatically replaced with the resolved VIN.
