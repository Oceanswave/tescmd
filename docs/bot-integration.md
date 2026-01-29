# Bot Integration

tescmd is designed for automation. This document covers everything needed to integrate tescmd into bots, scripts, cron jobs, and CI/CD pipelines.

## JSON Output

### Auto-Detection

When stdout is not a TTY (i.e., output is piped or captured), tescmd automatically switches to JSON output. No flags needed:

```bash
# These produce JSON:
result=$(tescmd vehicle list)
tescmd charge status | jq '.battery_level'
tescmd vehicle data > vehicle_state.json
```

To force JSON in an interactive terminal:

```bash
tescmd vehicle list --format json
```

### JSON Envelope

All JSON output follows a consistent envelope:

```json
{
  "ok": true,
  "command": "vehicle.list",
  "data": [ ... ],
  "timestamp": "2025-01-15T10:30:00Z"
}
```

**Error responses:**

```json
{
  "ok": false,
  "command": "charge.start",
  "error": {
    "code": "vehicle_asleep",
    "message": "Vehicle is asleep. Wake it first with: tescmd vehicle wake"
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### Data Shapes by Command Group

**`vehicle list`:**
```json
{
  "ok": true,
  "command": "vehicle.list",
  "data": [
    {
      "vin": "5YJ3E1EA1NF000000",
      "display_name": "My Model 3",
      "state": "online",
      "vehicle_id": 123456789
    }
  ]
}
```

**`vehicle data`:**
```json
{
  "ok": true,
  "command": "vehicle.data",
  "data": {
    "vin": "5YJ3E1EA1NF000000",
    "charge_state": {
      "battery_level": 72,
      "battery_range": 215.5,
      "charge_limit_soc": 80,
      "charging_state": "Disconnected",
      "charge_rate": 0,
      "charger_voltage": 0,
      "charger_actual_current": 0,
      "charge_port_door_open": false,
      "scheduled_charging_start_time": null
    },
    "climate_state": {
      "inside_temp": 21.5,
      "outside_temp": 15.0,
      "driver_temp_setting": 22.0,
      "passenger_temp_setting": 22.0,
      "is_climate_on": false,
      "fan_status": 0,
      "defrost_mode": 0
    },
    "drive_state": {
      "latitude": 37.3861,
      "longitude": -122.0839,
      "heading": 180,
      "speed": null,
      "power": 0,
      "shift_state": null
    },
    "vehicle_state": {
      "locked": true,
      "odometer": 15234.5,
      "sentry_mode": true,
      "car_version": "2025.2.6"
    }
  }
}
```

**`charge status`:**
```json
{
  "ok": true,
  "command": "charge.status",
  "data": {
    "battery_level": 72,
    "battery_range": 215.5,
    "charge_limit_soc": 80,
    "charging_state": "Charging",
    "charge_rate": 32.0,
    "charger_voltage": 240,
    "charger_actual_current": 32,
    "minutes_to_full_charge": 95,
    "charge_port_door_open": true,
    "charger_type": "AC"
  }
}
```

**Command responses (actions like `charge start`, `security lock`, etc.):**
```json
{
  "ok": true,
  "command": "charge.start",
  "data": {
    "result": true,
    "reason": ""
  }
}
```

## Exit Codes

| Code | Meaning | Example |
|------|---------|---------|
| `0` | Success | Command executed, data returned |
| `1` | General error | Unknown command, invalid args |
| `2` | Authentication error | No token, token expired and refresh failed |
| `3` | Vehicle error | Vehicle asleep, vehicle offline, vehicle not found |
| `4` | Command failed | Vehicle rejected the command |
| `5` | Network error | API unreachable, timeout |
| `6` | Configuration error | Missing client_id, invalid profile |

Use exit codes for control flow:

```bash
tescmd charge start --quiet
case $? in
  0) echo "Charging started" ;;
  3) echo "Vehicle is asleep, waking..." && tescmd vehicle wake --wait && tescmd charge start ;;
  4) echo "Command failed (maybe not plugged in?)" ;;
  *) echo "Error occurred" ;;
esac
```

## Headless Authentication

Bots can't open a browser. Two approaches:

### Approach 1: Token Transfer

Authenticate on a machine with a browser, then export:

```bash
# On your workstation
tescmd auth login
tescmd auth export > /secure/path/tokens.json

# On the bot/server
tescmd auth import < /secure/path/tokens.json
```

tescmd will automatically refresh the access token using the refresh token. No further browser interaction needed unless the refresh token is revoked.

### Approach 2: Environment Variables

Set tokens directly via environment:

```bash
export TESLA_ACCESS_TOKEN="eyJ..."
export TESLA_REFRESH_TOKEN="eyJ..."
export TESLA_CLIENT_ID="your-client-id"
export TESLA_CLIENT_SECRET="your-client-secret"
```

When `TESLA_ACCESS_TOKEN` is set, tescmd uses it directly and handles refresh automatically if `TESLA_REFRESH_TOKEN` and client credentials are also available.

## Environment Variable Configuration

Full list of environment variables for bot configuration:

```bash
# Required
TESLA_CLIENT_ID=your-client-id
TESLA_CLIENT_SECRET=your-client-secret

# Authentication (one of these methods)
TESLA_ACCESS_TOKEN=eyJ...         # direct token
TESLA_REFRESH_TOKEN=eyJ...        # for auto-refresh

# Vehicle selection
TESLA_VIN=5YJ3E1EA1NF000000      # default VIN (avoids interactive picker)

# Regional
TESLA_REGION=na                    # na, eu, cn

# Output
TESLA_OUTPUT_FORMAT=json           # force JSON everywhere

# Paths
TESLA_CONFIG_DIR=/etc/tescmd       # config directory
TESLA_TOKEN_FILE=/etc/tescmd/token # token file (instead of keyring)
```

## Piping Patterns

### Query and Extract

```bash
# Get battery level
tescmd charge status | jq -r '.data.battery_level'

# Get vehicle location as "lat,lng"
tescmd vehicle location | jq -r '.data | "\(.latitude),\(.longitude)"'

# Get interior temperature
tescmd climate status | jq -r '.data.inside_temp'

# List all VINs
tescmd vehicle list | jq -r '.data[].vin'
```

### Conditional Actions

```bash
# Charge if battery below 50%
level=$(tescmd charge status | jq -r '.data.battery_level')
if [ "$level" -lt 50 ]; then
  tescmd charge start --quiet
fi
```

### Cron Jobs

```bash
# crontab: Start preconditioning at 7 AM weekdays
0 7 * * 1-5 TESLA_VIN=5YJ3E1EA1NF000000 tescmd climate on --quiet

# crontab: Log vehicle state every 15 minutes
*/15 * * * * tescmd vehicle data >> /var/log/tesla/state.jsonl
```

### Chaining Commands

```bash
# Wake, then start charging
tescmd vehicle wake --wait --quiet && tescmd charge start

# Set climate and navigate
tescmd climate set --temp 72 --quiet && tescmd nav set "Work address"
```

## Error Handling for Bots

### Retry with Wake

Many commands fail if the vehicle is asleep. A common pattern:

```bash
run_command() {
  local output
  output=$(tescmd "$@" 2>/dev/null)
  local code=$?

  if [ $code -eq 3 ]; then
    # Vehicle asleep — wake and retry
    tescmd vehicle wake --wait --quiet
    output=$(tescmd "$@" 2>/dev/null)
    code=$?
  fi

  echo "$output"
  return $code
}

run_command charge start
```

### JSON Error Parsing

```bash
output=$(tescmd charge start)
ok=$(echo "$output" | jq -r '.ok')

if [ "$ok" != "true" ]; then
  error_code=$(echo "$output" | jq -r '.error.code')
  error_msg=$(echo "$output" | jq -r '.error.message')
  echo "Failed: [$error_code] $error_msg" >&2
fi
```

## Quiet Mode

`--quiet` suppresses all stdout and writes only errors to stderr. Use when you only care about the exit code:

```bash
tescmd charge start --quiet && echo "OK" || echo "FAIL"
```

## Rate Limiting

Tesla's Fleet API has rate limits. tescmd:

- Returns exit code `5` with error code `rate_limited` when rate-limited
- Includes `retry_after` in the JSON error response
- Does **not** automatically retry on rate limits (bots should implement their own backoff)

```json
{
  "ok": false,
  "command": "vehicle.data",
  "error": {
    "code": "rate_limited",
    "message": "Rate limited. Retry after 30 seconds.",
    "retry_after": 30
  }
}
```
