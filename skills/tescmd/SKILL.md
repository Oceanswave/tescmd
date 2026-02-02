---
name: tescmd
description: Use when querying or controlling Tesla vehicles, energy products, or Supercharger billing via the Fleet API — covers vehicle state, commands, telemetry triggers, MCP tools, and OpenClaw dispatch
---

# tescmd — Tesla Fleet API CLI

Query data from and send commands to Tesla vehicles, energy products, and Supercharger billing via the Tesla Fleet API. Supports CLI invocation, MCP tool calls, and OpenClaw gateway dispatch.

## Prefer MCP or OpenClaw Over Direct CLI

**Every direct CLI call to the Tesla Fleet API is billable** — including 4xx errors like "vehicle asleep" (408) and rate limits (429). There is no free tier.

If `tescmd serve` is running (MCP + telemetry), **always prefer the MCP tools or OpenClaw gateway** over spawning CLI subprocesses:

| Method | Read cost | Write cost | Best for |
|--------|-----------|------------|----------|
| **MCP tool** (via `tescmd serve`) | **Free** — reads served from telemetry-warmed cache | Billable (1 API call) | Agents connected to MCP server |
| **OpenClaw dispatch** (via gateway) | **Free** — reads served from in-memory telemetry store | Billable (1 API call) | Bots connected to OpenClaw gateway |
| **Direct CLI** (`tescmd --format json`) | Billable per call (cached 30s–1h) | Billable per call | Fallback when no server is running |

**Why this matters:** A naive script polling `vehicle_data` every 5 minutes generates ~1,000+ billable requests/day. With `tescmd serve` running, telemetry pushes data for free and the MCP/OpenClaw read paths serve it from cache at zero cost. Only write commands (lock, charge, climate) hit the API.

**Decision flow:**
1. Is `tescmd serve` running? → Use MCP tools or OpenClaw dispatch
2. No server? → Fall back to direct CLI with `--format json --wake`

## Direct CLI Invocation (Fallback)

When no MCP/OpenClaw server is available, use these flags:

```bash
tescmd --format json --wake <command> [args]
```

| Flag | Purpose |
|------|---------|
| `--format json` | Structured JSON on stdout (required for parsing) |
| `--wake` | Auto-wake vehicle without interactive prompts (billable) |
| `--fresh` | Bypass cache for this call |
| `--units metric` | All values in °C, km, bar (default: °F, mi, psi) |
| `--vin VIN` | Target vehicle (or set `TESLA_VIN`) |

VIN can also be passed positionally: `tescmd --format json --wake charge status 5YJ3E1EA...`

## JSON Envelope

All commands return:

```json
{"ok": true, "command": "charge.status", "data": {...}, "timestamp": "...", "_cache": {"hit": true, "age_seconds": 15, "ttl": 60}}
```

On error: `{"ok": false, "error": {"code": "auth_failed", "message": "..."}, "command": "..."}`

Error codes: `auth_failed` (re-login needed), `vehicle_asleep` (use `--wake`), `tier_readonly` (run `tescmd setup`), `key_not_enrolled` (run `tescmd key enroll`), `missing_scopes` (re-login with scopes).

## Caching

Read commands are cached with tiered TTLs: static data (specs, warranty) 1h, fleet lists 5m, standard queries 1m, location/speed 30s. Write commands auto-invalidate the cache. Use `--fresh` to bypass.

---

## Vehicle State Queries

### vehicle

| Command | Description | Key response fields |
|---------|-------------|---------------------|
| `vehicle list` | All vehicles on account | `data[].vin`, `data[].display_name`, `data[].state` |
| `vehicle info [VIN]` | Full vehicle data snapshot | `data.vehicle_state`, `data.charge_state`, `data.drive_state`, `data.climate_state` |
| `vehicle data [VIN]` | Full data (same as info) | Same as above |
| `vehicle get [VIN]` | Lightweight basic info | `data.vin`, `data.display_name`, `data.state` |
| `vehicle location [VIN]` | GPS coordinates | `data.drive_state.latitude`, `data.drive_state.longitude` |
| `vehicle alerts [VIN]` | Recent alerts | `data.recent_alerts[]` |
| `vehicle nearby-chargers [VIN]` | Nearby Superchargers | `data.superchargers[]`, `data.destination_charging[]` |
| `vehicle release-notes [VIN]` | Firmware release notes | `data.release_notes_data` |
| `vehicle specs [VIN]` | Specifications | `data.*` (cached 1h) |
| `vehicle warranty [VIN]` | Warranty info | `data.*` (cached 1h) |
| `vehicle drivers [VIN]` | Authorized drivers | `data[]` |
| `vehicle fleet-status [VIN]` | Fleet telemetry status | `data.fleet_telemetry_config` |
| `vehicle subscriptions [VIN]` | Active subscriptions | `data[]` |
| `vehicle upgrades [VIN]` | Available upgrades | `data[]` |
| `vehicle options [VIN]` | Installed options | `data[]` |
| `vehicle service [VIN]` | Service data | `data.*` |
| `vehicle mobile-access [VIN]` | Mobile access enabled? | `data.response` (boolean) |

### charge

| Command | Description | Key response fields |
|---------|-------------|---------------------|
| `charge status [VIN]` | Battery, range, charge rate | `data.charge_state.battery_level`, `.battery_range`, `.charging_state`, `.charge_limit_soc` |

### climate

| Command | Description | Key response fields |
|---------|-------------|---------------------|
| `climate status [VIN]` | Temps, HVAC, seats | `data.climate_state.inside_temp`, `.outside_temp`, `.is_climate_on`, `.seat_heater_*` |

### security

| Command | Description | Key response fields |
|---------|-------------|---------------------|
| `security status [VIN]` | Locks, sentry, doors | `data.vehicle_state.locked`, `.sentry_mode`, `.fd_window`, `.df` |

### software

| Command | Description | Key response fields |
|---------|-------------|---------------------|
| `software status [VIN]` | Version, update status | `data.vehicle_state.car_version`, `.software_update` |

### energy

| Command | Description |
|---------|-------------|
| `energy list` | List Powerwall/Solar sites |
| `energy status SITE_ID` | Site info |
| `energy live SITE_ID` | Real-time power flow |
| `energy history SITE_ID [--start DATE] [--end DATE]` | Historical data |
| `energy telemetry SITE_ID` | Site telemetry |

### billing

| Command | Description |
|---------|-------------|
| `billing history [--vin VIN] [--start ISO] [--end ISO]` | Supercharger billing history |
| `billing sessions [--vin VIN] [--from ISO] [--to ISO]` | Charging sessions |
| `billing invoice ID [-o PATH]` | Download invoice |

### user

| Command | Description |
|---------|-------------|
| `user me` | Account info |
| `user region` | Regional API endpoint |
| `user orders` | Vehicle orders |
| `user features` | Feature flags |

### Other reads

| Command | Description |
|---------|-------------|
| `auth status` | Token/auth status |
| `cache status` | Cache hit rates, entry counts |
| `status` | Full configuration overview |
| `partner public-key --domain D` | Public key for domain |
| `partner telemetry-error-vins` | VINs with telemetry errors |
| `partner telemetry-errors` | Telemetry error details |
| `sharing list-invites [VIN]` | Sharing invites |
| `raw get PATH [--params JSON]` | Raw Fleet API GET |

---

## Vehicle Commands (Write)

All write commands require `--wake` for unattended use. Commands using the Vehicle Command Protocol are signed automatically when keys are enrolled.

### charge

| Command | Description |
|---------|-------------|
| `charge start [VIN]` | Start charging |
| `charge stop [VIN]` | Stop charging |
| `charge limit [VIN] PCT` | Set charge limit (50–100) |
| `charge limit-max [VIN]` | Set limit to max range |
| `charge limit-std [VIN]` | Set limit to standard |
| `charge amps [VIN] AMPS` | Set charge current (amps) |
| `charge port-open [VIN]` | Open charge port |
| `charge port-close [VIN]` | Close charge port |
| `charge schedule [VIN] [--enable\|--disable] [--time MIN]` | Scheduled charging |
| `charge departure [VIN] --time MIN [--precondition]` | Scheduled departure |
| `charge add-schedule [VIN] --id ID [--name N] [--days-of-week D]` | Add charge schedule |
| `charge remove-schedule [VIN] --id ID` | Remove charge schedule |
| `charge clear-schedules [VIN] [--home] [--work] [--other]` | Batch remove schedules |
| `charge managed-amps [VIN] AMPS` | Fleet managed charging current |
| `charge managed-location [VIN] --lat LAT --lon LON` | Fleet managed charger location |
| `charge managed-schedule [VIN] MINUTES` | Fleet managed schedule |

### climate

| Command | Description |
|---------|-------------|
| `climate on [VIN]` | Turn on climate |
| `climate off [VIN]` | Turn off climate |
| `climate set [VIN] TEMP [--passenger T] [--celsius]` | Set cabin temperature |
| `climate precondition [VIN] [--on\|--off]` | Max preconditioning |
| `climate seat [VIN] SEAT LEVEL` | Seat heater (SEAT: driver, passenger, rear-left, rear-center, rear-right; LEVEL: 0–3) |
| `climate seat-cool [VIN] SEAT LEVEL` | Seat cooler (0–3) |
| `climate wheel-heater [VIN] [--on\|--off]` | Steering wheel heater |
| `climate wheel-level [VIN] LEVEL` | Wheel heat level (0–3) |
| `climate overheat [VIN] [--on\|--off] [--fan-only]` | Cabin overheat protection |
| `climate cop-temp [VIN] LEVEL` | Overheat temp (0=low, 1=med, 2=high) |
| `climate bioweapon [VIN] [--on\|--off]` | Bioweapon defense mode |
| `climate keeper [VIN] MODE` | Climate keeper (off, on, dog, camp) |
| `climate auto-seat [VIN] SEAT [--on\|--off]` | Auto seat climate |
| `climate auto-wheel [VIN] [--on\|--off]` | Auto steering wheel heat |

### security

| Command | Description |
|---------|-------------|
| `security lock [VIN]` | Lock all doors |
| `security unlock [VIN]` | Unlock all doors |
| `security auto-secure [VIN]` | Close falcon wings + lock (Model X) |
| `security sentry [VIN] [--on\|--off]` | Toggle sentry mode |
| `security flash [VIN]` | Flash the lights |
| `security honk [VIN]` | Honk the horn |
| `security boombox [VIN] [--enable\|--disable]` | Boombox mode |
| `security remote-start [VIN]` | Enable remote start |
| `security valet [VIN] [--on\|--off]` | Toggle valet mode |
| `security valet-reset [VIN]` | Reset valet PIN |
| `security pin-to-drive [VIN] [--on\|--off] [--pin P]` | PIN to drive |
| `security pin-reset [VIN] [--new-pin P]` | Reset PIN |
| `security pin-clear-admin [VIN]` | Clear PIN (admin) |
| `security speed-limit [VIN] MPH [--pin P]` | Set speed limit |
| `security speed-clear [VIN]` | Clear speed limit |
| `security speed-clear-admin [VIN]` | Clear speed limit (admin) |
| `security guest-mode [VIN] [--on\|--off] [--pin P]` | Toggle guest mode |
| `security erase-data [VIN]` | Factory reset vehicle data |

### trunk

| Command | Description |
|---------|-------------|
| `trunk open [VIN]` | Open rear trunk |
| `trunk close [VIN]` | Close rear trunk |
| `trunk frunk [VIN]` | Open front trunk |
| `trunk window [VIN] --state vent\|close\|stop` | Control windows |
| `trunk sunroof [VIN] --state vent\|close\|stop` | Control sunroof |
| `trunk tonneau-open [VIN]` | Open tonneau cover |
| `trunk tonneau-close [VIN]` | Close tonneau cover |
| `trunk tonneau-stop [VIN]` | Stop tonneau cover |

### media

| Command | Description |
|---------|-------------|
| `media play-pause [VIN]` | Toggle playback |
| `media next-track [VIN]` | Next track |
| `media prev-track [VIN]` | Previous track |
| `media next-fav [VIN]` | Next favorite |
| `media prev-fav [VIN]` | Previous favorite |
| `media volume-up [VIN]` | Volume up |
| `media volume-down [VIN]` | Volume down |
| `media adjust-volume [VIN] LEVEL` | Set volume level |

### nav

| Command | Description |
|---------|-------------|
| `nav send [VIN] ADDRESS` | Send destination to nav |
| `nav gps [VIN] LAT,LON [--order N]` | Navigate to GPS coordinates |
| `nav supercharger [VIN]` | Navigate to nearest Supercharger |
| `nav homelink [VIN]` | Trigger HomeLink |
| `nav waypoints [VIN] JSON` | Multi-stop route |

### software

| Command | Description |
|---------|-------------|
| `software schedule [VIN] SECS` | Schedule update in N seconds |
| `software cancel [VIN]` | Cancel pending update |

### energy (write)

| Command | Description |
|---------|-------------|
| `energy backup SITE_ID PCT` | Set backup reserve % |
| `energy mode SITE_ID MODE` | Operation mode (self_consumption, backup, autonomous) |
| `energy storm SITE_ID [--on\|--off]` | Storm response |
| `energy tou SITE_ID [--on\|--off]` | Time-of-use mode |
| `energy off-grid SITE_ID PCT` | Off-grid reserve % |
| `energy grid-config SITE_ID [--min-reserve R]` | Grid settings |
| `energy calendar SITE_ID JSON` | Send calendar to site |

### vehicle (write)

| Command | Description |
|---------|-------------|
| `vehicle wake [VIN]` | Wake vehicle |
| `vehicle rename [VIN] NAME` | Rename vehicle |
| `vehicle low-power [VIN] [--on\|--off]` | Low-power mode |
| `vehicle accessory-power [VIN] [--on\|--off]` | Accessory power |
| `vehicle calendar [VIN] JSON` | Send calendar entries |

### sharing

| Command | Description |
|---------|-------------|
| `sharing add-driver [VIN] EMAIL` | Add driver by email |
| `sharing remove-driver [VIN] USER_ID` | Remove driver |
| `sharing create-invite [VIN] EMAIL` | Create sharing invite |
| `sharing redeem-invite [VIN] INVITE_ID` | Redeem invite |
| `sharing revoke-invite [VIN] INVITE_ID` | Revoke invite |

### Other writes

| Command | Description |
|---------|-------------|
| `cache clear [--vin V] [--site S] [--scope account\|partner]` | Clear cache |
| `raw post PATH [--body JSON]` | Raw Fleet API POST |

---

## Trigger Subscriptions

Register conditions on telemetry fields. Available via MCP tools (`trigger_create`, etc.) and OpenClaw dispatch (`trigger.create`, etc.).

### Operators

| Operator | Value | Example |
|----------|-------|---------|
| `lt` | Numeric threshold | Battery < 20 |
| `gt` | Numeric threshold | Speed > 80 |
| `lte` | Numeric threshold | Temp <= 32 |
| `gte` | Numeric threshold | Temp >= 100 |
| `eq` | Any (string, number, bool) | ChargeState == "Charging" |
| `neq` | Any | Gear != "P" |
| `changed` | None (omit value) | Fires when value differs from previous |
| `enter` | `{latitude, longitude, radius_m}` | Vehicle enters geofence |
| `leave` | `{latitude, longitude, radius_m}` | Vehicle leaves geofence |

### Firing modes

- **One-shot** (`once: true`): fires once, auto-deletes
- **Persistent** (`once: false`, default): fires repeatedly with `cooldown_seconds` (default 60s)

### MCP trigger tools

**`trigger_create`** — Create a trigger.

```json
{"field": "BatteryLevel", "operator": "lt", "value": 20}
```

Returns: `{"id": "a1b2c3d4e5f6", "field": "BatteryLevel", "operator": "lt"}`

Optional params: `once` (bool), `cooldown_seconds` (float).

Geofence example:

```json
{"field": "Location", "operator": "enter", "value": {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 500}}
```

**`trigger_delete`** — Delete by ID: `{"id": "a1b2c3d4e5f6"}`

**`trigger_list`** — List all triggers. Returns `{"triggers": [...]}`

**`trigger_poll`** — Drain pending notifications. Returns `{"notifications": [{trigger_id, field, operator, threshold, value, previous_value, fired_at, vin}, ...]}`

### Limits

Max 100 triggers. Max 500 pending notifications (oldest dropped on overflow).

### Common telemetry field names

| Field | Type | Trigger example |
|-------|------|-----------------|
| `BatteryLevel` | 0–100 | `{operator: "lt", value: 20}` |
| `InsideTemp` | °F | `{operator: "gt", value: 100}` |
| `OutsideTemp` | °F | `{operator: "lt", value: 32}` |
| `Location` | `{latitude, longitude, heading, speed}` | Geofence `enter`/`leave` |
| `VehicleSpeed` | mph | `{operator: "gt", value: 80}` |
| `ChargeState` | string | `{operator: "eq", value: "Charging"}` |
| `Gear` | string (P/D/R/N) | `{operator: "changed"}` |
| `Locked` | bool | `{operator: "eq", value: false}` |
| `SentryMode` | bool | `{operator: "changed"}` |

---

## OpenClaw Gateway Commands

When connected via OpenClaw (`tescmd serve --openclaw ws://...` or `tescmd openclaw bridge`), bots dispatch commands through the gateway. These use dot-notation.

### Read commands

| Command | Description |
|---------|-------------|
| `location.get` | Vehicle location |
| `battery.get` | Battery level and range |
| `temperature.get` | Inside/outside temps |
| `speed.get` | Vehicle speed |
| `charge_state.get` | Charge state |
| `security.get` | Lock/sentry status |
| `trigger.list` | List triggers |
| `trigger.poll` | Drain pending notifications |

### Write commands

| Command | Description |
|---------|-------------|
| `door.lock` | Lock doors |
| `door.unlock` | Unlock doors |
| `climate.on` | Turn on climate |
| `climate.off` | Turn off climate |
| `climate.set_temp` | Set temperature (`{temp}`) |
| `charge.start` | Start charging |
| `charge.stop` | Stop charging |
| `charge.set_limit` | Set charge limit (`{percent}`) |
| `trunk.open` | Open rear trunk |
| `frunk.open` | Open front trunk |
| `flash_lights` | Flash the lights |
| `honk_horn` | Honk the horn |
| `sentry.on` | Enable sentry mode |
| `sentry.off` | Disable sentry mode |
| `system.run` | Meta-dispatch any command by name |

### Trigger commands (via gateway)

| Command | Params |
|---------|--------|
| `trigger.create` | `{field, operator, value?, once?, cooldown_seconds?}` |
| `trigger.delete` | `{id}` |
| `trigger.list` | `{}` |
| `trigger.poll` | `{}` |
| `cabin_temp.trigger` | `{operator, value?, once?, cooldown_seconds?}` (pre-fills field=InsideTemp) |
| `outside_temp.trigger` | `{operator, value?, once?, cooldown_seconds?}` (pre-fills field=OutsideTemp) |
| `battery.trigger` | `{operator, value?, once?, cooldown_seconds?}` (pre-fills field=BatteryLevel) |
| `location.trigger` | `{operator, value?, once?, cooldown_seconds?}` (pre-fills field=Location) |

### `system.run` aliases

`system.run` accepts both OpenClaw-style and API-style names:

| API-style name | Resolves to |
|----------------|-------------|
| `door_lock` | `door.lock` |
| `door_unlock` | `door.unlock` |
| `auto_conditioning_start` | `climate.on` |
| `auto_conditioning_stop` | `climate.off` |
| `set_temps` | `climate.set_temp` |
| `charge_start` | `charge.start` |
| `charge_stop` | `charge.stop` |
| `set_charge_limit` | `charge.set_limit` |
| `actuate_trunk` | `trunk.open` |
| `flash_lights` | `flash_lights` |
| `honk_horn` | `honk_horn` |

Example: `{"method": "system.run", "params": {"method": "door_lock", "params": {}}}`

---

## Server Modes

Start `tescmd serve` first, then use MCP tools or OpenClaw dispatch for all reads — this eliminates per-request API costs for vehicle state queries.

### `tescmd serve` (recommended)

Combined MCP + telemetry + OpenClaw with TUI dashboard. Telemetry pushes keep the cache warm so MCP reads are free:

```bash
tescmd serve VIN                                    # MCP + telemetry TUI
tescmd serve VIN --openclaw ws://gw:18789           # + OpenClaw bridge
tescmd serve VIN --no-mcp                           # Telemetry-only TUI
tescmd serve --no-telemetry                         # MCP-only (no VIN needed)
tescmd serve --transport stdio                      # MCP stdio for Claude Desktop
```

### `tescmd mcp serve`

Standalone MCP server (legacy, prefer `tescmd serve`):

```bash
tescmd mcp serve --transport streamable-http --port 8080
tescmd mcp serve --transport stdio
```

### `tescmd openclaw bridge`

Standalone OpenClaw bridge:

```bash
tescmd openclaw bridge VIN --gateway ws://gw:18789 --token SECRET
tescmd openclaw bridge --dry-run                    # JSONL output, no gateway
```

---

## Common Patterns

### Check battery and conditionally start charging

```bash
# Read battery
RESULT=$(tescmd --format json --wake charge status VIN)
LEVEL=$(echo "$RESULT" | jq '.data.charge_state.battery_level')

# Start charging if low
if [ "$LEVEL" -lt 20 ]; then
  tescmd --format json --wake charge start VIN
fi
```

### Find the vehicle

```bash
tescmd --format json --wake vehicle location VIN
# → data.drive_state.latitude, data.drive_state.longitude
```

### Lock and verify

```bash
tescmd --format json --wake security lock VIN
tescmd --format json --wake --fresh security status VIN
# → data.vehicle_state.locked == true
```

### Set up a low-battery trigger (MCP)

Call `trigger_create` tool with: `{"field": "BatteryLevel", "operator": "lt", "value": 20, "once": true}`

Then periodically call `trigger_poll` to check for notifications.

### Set up a geofence trigger (MCP)

```json
{"field": "Location", "operator": "leave", "value": {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 200}}
```

Fires when vehicle leaves the 200m radius around the specified point.
