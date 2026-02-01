# Bot Integration

tescmd is designed for automation. This document covers everything needed to integrate tescmd into bots, scripts, cron jobs, and CI/CD pipelines.

## JSON Output

### Auto-Detection

When stdout is not a TTY (i.e., output is piped or captured), tescmd automatically switches to JSON output. No flags needed:

```bash
# These produce JSON:
result=$(tescmd vehicle list)
tescmd vehicle data | jq '.charge_state.battery_level'
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
  "command": "vehicle.data",
  "error": {
    "code": "vehicle_asleep",
    "message": "Vehicle is asleep. Wake it first with: tescmd vehicle wake"
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### Data Shapes by Command

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

JSON output returns raw API values (Celsius, miles, bar) regardless of display unit settings:

```json
{
  "ok": true,
  "command": "vehicle.data",
  "data": {
    "vin": "5YJ3E1EA1NF000000",
    "charge_state": {
      "battery_level": 72,
      "battery_range": 215.5,
      "ideal_battery_range": 230.0,
      "est_battery_range": 200.0,
      "usable_battery_level": 70,
      "charge_limit_soc": 80,
      "charging_state": "Disconnected",
      "charge_rate": 0,
      "charger_voltage": 0,
      "charger_actual_current": 0,
      "charger_power": 0,
      "charger_type": null,
      "charge_energy_added": 0.0,
      "charge_miles_added_rated": 0.0,
      "charge_port_door_open": false,
      "charge_port_latch": "Disengaged",
      "conn_charge_cable": "<invalid>",
      "minutes_to_full_charge": 0,
      "time_to_full_charge": 0.0,
      "scheduled_charging_start_time": null,
      "scheduled_charging_mode": "Off",
      "battery_heater_on": false,
      "preconditioning_enabled": false
    },
    "climate_state": {
      "inside_temp": 21.5,
      "outside_temp": 15.0,
      "driver_temp_setting": 22.0,
      "passenger_temp_setting": 22.0,
      "is_climate_on": false,
      "fan_status": 0,
      "defrost_mode": 0,
      "seat_heater_left": 0,
      "seat_heater_right": 0,
      "seat_heater_rear_left": 0,
      "seat_heater_rear_center": 0,
      "seat_heater_rear_right": 0,
      "steering_wheel_heater": false,
      "cabin_overheat_protection": "Off",
      "cabin_overheat_protection_actively_cooling": false,
      "is_auto_conditioning_on": false,
      "is_preconditioning": false,
      "bioweapon_defense_mode": false
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
      "car_version": "2025.2.6",
      "door_driver_front": 0,
      "door_driver_rear": 0,
      "door_passenger_front": 0,
      "door_passenger_rear": 0,
      "window_driver_front": 0,
      "window_driver_rear": 0,
      "window_passenger_front": 0,
      "window_passenger_rear": 0,
      "ft": 0,
      "rt": 0,
      "center_display_state": 0,
      "dashcam_state": "Recording",
      "remote_start_enabled": false,
      "is_user_present": false,
      "homelink_nearby": false,
      "tpms_pressure_fl": 2.9,
      "tpms_pressure_fr": 3.0,
      "tpms_pressure_rl": 2.85,
      "tpms_pressure_rr": 2.9
    },
    "vehicle_config": {
      "car_type": "modely",
      "trim_badging": "74d",
      "exterior_color": "MidnightSilver",
      "wheel_type": "Gemini19",
      "roof_color": "Glass",
      "can_accept_navigation_requests": true,
      "can_actuate_trunks": true,
      "has_seat_cooling": false,
      "motorized_charge_port": true,
      "plg": true,
      "eu_vehicle": false
    },
    "gui_settings": {
      "gui_distance_units": "mi/hr",
      "gui_temperature_units": "F",
      "gui_charge_rate_units": "mi/hr"
    }
  }
}
```

> **Note on units:** JSON output always returns raw API values — temperatures in Celsius, distances in miles, tire pressures in bar. The unit conversion system (`DisplayUnits`) only affects Rich terminal output. Scripts should handle conversion themselves if needed.

**Command responses (actions like `vehicle wake`):**
```json
{
  "ok": true,
  "command": "vehicle.wake",
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
tescmd vehicle wake --quiet
case $? in
  0) echo "Vehicle is awake" ;;
  3) echo "Vehicle is offline" ;;
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
tescmd vehicle data | jq -r '.data.charge_state.battery_level'

# Get vehicle location as "lat,lng"
tescmd vehicle location | jq -r '.data | "\(.latitude),\(.longitude)"'

# Get interior temperature (returns Celsius)
tescmd vehicle data | jq -r '.data.climate_state.inside_temp'

# List all VINs
tescmd vehicle list | jq -r '.data[].vin'

# Get tire pressure in bar (raw API value)
tescmd vehicle data | jq -r '.data.vehicle_state | "FL: \(.tpms_pressure_fl), FR: \(.tpms_pressure_fr)"'
```

### Cron Jobs

```bash
# crontab: Log vehicle state every 15 minutes
*/15 * * * * tescmd vehicle data >> /var/log/tesla/state.jsonl
```

### Chaining Commands

```bash
# Wake, then get data
tescmd vehicle wake --wait --quiet && tescmd vehicle data
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

run_command vehicle data
```

### JSON Error Parsing

```bash
output=$(tescmd vehicle data)
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
tescmd vehicle wake --quiet && echo "OK" || echo "FAIL"
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

## Telemetry Streaming for Bots

For bots that need continuous vehicle data, `tescmd vehicle telemetry stream` offers a push-based alternative to polling. When piped or run with `--format json`, it emits one JSON line per telemetry frame:

```bash
# Stream telemetry as JSONL (one JSON object per line)
tescmd vehicle telemetry stream --format json

# Stream specific field presets
tescmd vehicle telemetry stream --fields driving --format json   # speed, location, power
tescmd vehicle telemetry stream --fields charging --format json  # battery, voltage, current
tescmd vehicle telemetry stream --fields climate --format json   # temps, HVAC state
tescmd vehicle telemetry stream --fields all --format json       # all 120+ fields

# Override polling interval
tescmd vehicle telemetry stream --interval 5 --format json       # every 5 seconds
```

### Processing Telemetry in a Bot

```bash
# Log telemetry to a file
tescmd vehicle telemetry stream --format json >> /var/log/tesla/telemetry.jsonl

# Process in real-time with jq
tescmd vehicle telemetry stream --format json | while read -r line; do
  field=$(echo "$line" | jq -r '.field')
  value=$(echo "$line" | jq -r '.value')
  echo "[$field] $value"
done
```

### Cost Advantage

Telemetry streaming costs only 2 API requests (create config + delete config) regardless of how long the stream runs or how much data flows. Compared to polling `vehicle_data` every 5 seconds (~17,280 requests/day), streaming reduces API costs by over 99%.

**Requirements:** `pip install tescmd[telemetry]` and Tailscale with Funnel enabled on the host machine.
