---
name: tescmd
description: Query and control Tesla vehicles via the Fleet API
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: ["tescmd"]
      env: ["TESLA_ACCESS_TOKEN"]
    emoji: "\U0001F697"
---

# tescmd — Tesla Fleet API CLI

Query data from and send commands to Tesla vehicles via the Tesla Fleet API.

## Quick Reference

**Always use these flags for agent invocation:**

```bash
tescmd --format json --wake <command> [args]
```

- `--format json` — structured JSON output on stdout (no Rich formatting)
- `--wake` — auto-wake the vehicle without interactive prompts (billable)

## JSON Envelope

All commands return a JSON envelope:

```json
{
  "ok": true,
  "command": "charge.status",
  "data": { ... },
  "timestamp": "2026-01-31T12:00:00Z",
  "_cache": { "hit": true, "age_seconds": 15, "ttl": 60 }
}
```

On error:

```json
{
  "ok": false,
  "error": { "code": "auth_failed", "message": "..." },
  "command": "charge.status"
}
```

## VIN Resolution

Most commands accept a VIN positionally or via `--vin`:

```bash
tescmd --format json --wake charge status 5YJ3E1EA1NF000001
tescmd --format json --wake --vin 5YJ3E1EA1NF000001 charge status
```

If `TESLA_VIN` is set, the VIN can be omitted.

## Command Groups

### Vehicle (`vehicle`)

| Command | Type | Description |
|---------|------|-------------|
| `vehicle list` | read | List all vehicles on the account |
| `vehicle info [VIN]` | read | Vehicle info summary |
| `vehicle data [VIN]` | read | Full vehicle data (all states) |
| `vehicle location [VIN]` | read | GPS coordinates |
| `vehicle wake [VIN]` | write | Wake the vehicle |
| `vehicle rename [VIN] NAME` | write | Rename the vehicle |
| `vehicle alerts [VIN]` | read | Recent alerts |
| `vehicle nearby-chargers [VIN]` | read | Nearby Superchargers |
| `vehicle release-notes [VIN]` | read | Software release notes |
| `vehicle specs [VIN]` | read | Vehicle specifications |
| `vehicle warranty [VIN]` | read | Warranty info |
| `vehicle drivers [VIN]` | read | Authorized drivers |
| `vehicle fleet-status [VIN]` | read | Fleet telemetry status |
| `vehicle subscriptions [VIN]` | read | Active subscriptions |

### Charge (`charge`)

| Command | Type | Description |
|---------|------|-------------|
| `charge status [VIN]` | read | Battery %, range, charge rate, limit |
| `charge start [VIN]` | write | Start charging |
| `charge stop [VIN]` | write | Stop charging |
| `charge limit [VIN] PCT` | write | Set charge limit (50-100) |
| `charge limit-max [VIN]` | write | Set limit to max range |
| `charge limit-std [VIN]` | write | Set limit to standard |
| `charge amps [VIN] AMPS` | write | Set charge current |
| `charge port-open [VIN]` | write | Open charge port |
| `charge port-close [VIN]` | write | Close charge port |

### Climate (`climate`)

| Command | Type | Description |
|---------|------|-------------|
| `climate status [VIN]` | read | Temps, HVAC, seats, defrost |
| `climate on [VIN]` | write | Turn on climate |
| `climate off [VIN]` | write | Turn off climate |
| `climate set [VIN] TEMP` | write | Set driver temp (F or C) |
| `climate precondition [VIN]` | write | Precondition cabin |
| `climate seat [VIN] SEAT LEVEL` | write | Set seat heater (0-3) |
| `climate wheel-heater [VIN] on/off` | write | Steering wheel heater |
| `climate bioweapon [VIN] on/off` | write | Bioweapon defense mode |

### Security (`security`)

| Command | Type | Description |
|---------|------|-------------|
| `security status [VIN]` | read | Locked, sentry, doors, windows |
| `security lock [VIN]` | write | Lock the vehicle |
| `security unlock [VIN]` | write | Unlock the vehicle |
| `security sentry [VIN] on/off` | write | Toggle sentry mode |
| `security flash [VIN]` | write | Flash the lights |
| `security honk [VIN]` | write | Honk the horn |
| `security remote-start [VIN]` | write | Enable remote start |
| `security valet [VIN] on/off` | write | Toggle valet mode |

### Trunk (`trunk`)

| Command | Type | Description |
|---------|------|-------------|
| `trunk open [VIN]` | write | Open the trunk |
| `trunk close [VIN]` | write | Close the trunk |
| `trunk frunk [VIN]` | write | Open the frunk |
| `trunk window [VIN] vent/close` | write | Vent or close windows |

### Media (`media`)

| Command | Type | Description |
|---------|------|-------------|
| `media play-pause [VIN]` | write | Toggle play/pause |
| `media next-track [VIN]` | write | Next track |
| `media prev-track [VIN]` | write | Previous track |
| `media volume [VIN] LEVEL` | write | Set volume (0-11) |

### Navigation (`nav`)

| Command | Type | Description |
|---------|------|-------------|
| `nav send [VIN] ADDRESS` | write | Send destination |
| `nav supercharger [VIN]` | write | Navigate to nearest Supercharger |

### Software (`software`)

| Command | Type | Description |
|---------|------|-------------|
| `software status [VIN]` | read | Update status/version |
| `software schedule [VIN] SECS` | write | Schedule update in N seconds |
| `software cancel [VIN]` | write | Cancel pending update |

### Energy (`energy`)

| Command | Type | Description |
|---------|------|-------------|
| `energy list` | read | List energy sites (Powerwall) |
| `energy status SITE_ID` | read | Site status |
| `energy live SITE_ID` | read | Live power flow |
| `energy history SITE_ID` | read | Historical data |
| `energy backup SITE_ID PCT` | write | Set backup reserve |
| `energy mode SITE_ID MODE` | write | Set operation mode |

### Billing (`billing`)

| Command | Type | Description |
|---------|------|-------------|
| `billing history` | read | Supercharger billing history |
| `billing sessions` | read | Charging sessions |
| `billing invoice ID` | read | Download invoice |

### User (`user`)

| Command | Type | Description |
|---------|------|-------------|
| `user me` | read | Account info |
| `user region` | read | Account region |
| `user orders` | read | Vehicle orders |
| `user features` | read | Feature flags |

### Cache (`cache`)

| Command | Type | Description |
|---------|------|-------------|
| `cache status` | read | Cache stats |
| `cache clear` | write | Clear all cache |
| `cache clear --vin VIN` | write | Clear cache for vehicle |

### Auth (`auth`)

| Command | Type | Description |
|---------|------|-------------|
| `auth status` | read | Token/auth status |
| `auth login` | interactive | OAuth login (opens browser) |
| `auth logout` | write | Remove stored tokens |
| `auth refresh` | write | Refresh access token |

## Common Patterns

### Get battery level

```bash
tescmd --format json --wake charge status 5YJ3E1EA1NF000001
```

Response `data.charge_state.battery_level` is the percentage.

### Check if vehicle is locked

```bash
tescmd --format json --wake security status 5YJ3E1EA1NF000001
```

Response `data.vehicle_state.locked` is boolean.

### Get vehicle location

```bash
tescmd --format json --wake vehicle location 5YJ3E1EA1NF000001
```

Response `data.drive_state.latitude` and `data.drive_state.longitude`.

### Set charge limit

```bash
tescmd --format json --wake charge limit 5YJ3E1EA1NF000001 80
```

### Lock the vehicle

```bash
tescmd --format json --wake security lock 5YJ3E1EA1NF000001
```

## Error Handling

Common error codes:
- `auth_failed` — token expired, run `tescmd auth login`
- `vehicle_asleep` — vehicle sleeping, use `--wake` flag
- `missing_scopes` — token lacks permissions, re-login
- `tier_readonly` — write commands need `tescmd setup` (full tier)
- `key_not_enrolled` — key enrollment needed for signed commands

## Caching

Read commands are cached (TTL: 30s-1h). Use `--fresh` to bypass:

```bash
tescmd --format json --wake --fresh charge status VIN
```

## Display Units

Override with `--units metric` or `--units us`:

```bash
tescmd --format json --wake --units metric climate status VIN
```
