# OpenClaw Bridge

The OpenClaw bridge streams filtered vehicle telemetry to an [OpenClaw](https://openclaw.ai/) Gateway, enabling real-time agent consumption of vehicle state. Unlike raw telemetry streaming, the bridge applies dual-gate filtering (delta threshold + throttle interval) to reduce noise and control event volume.

> **Combined mode:** `tescmd serve VIN --openclaw ws://...` combines MCP + cache warming + OpenClaw bridging in a single command. Use this when you want agents to have cached reads AND OpenClaw events simultaneously. The dedicated `openclaw bridge` command remains available for standalone bridge use.

## Quick Start

```bash
# Combined: MCP + cache warming + OpenClaw
tescmd serve 5YJ3... --openclaw ws://gateway.example.com:18789

# Standalone bridge to local gateway (default: ws://127.0.0.1:18789)
tescmd openclaw bridge

# Bridge to remote gateway with auth
tescmd openclaw bridge --gateway ws://gateway.example.com:18789 --token SECRET

# Dry-run: print filtered events as JSONL without connecting
tescmd openclaw bridge --dry-run
```

## Requirements

- **Tailscale** with Funnel enabled (the bridge exposes a local WebSocket server via Tailscale Funnel so Tesla can push telemetry to it)
- An OpenClaw Gateway to receive events (or use `--dry-run` to test without one)

## How It Works

The bridge connects two systems:

1. **Tesla Fleet Telemetry** pushes raw vehicle data to a local WebSocket server exposed via Tailscale Funnel
2. **OpenClaw Gateway** receives filtered, structured events over a persistent WebSocket connection

The data pipeline:

```
Tesla Vehicle
    → Fleet Telemetry push (protobuf over WebSocket)
        → TelemetryServer (local, exposed via Tailscale Funnel)
            → TelemetryDecoder (protobuf → TelemetryFrame)
                → DualGateFilter (delta + throttle)
                    → EventEmitter (TelemetryFrame → OpenClaw event)
                        → GatewayClient (WebSocket send)
                            → OpenClaw Gateway
```

## CLI Options

```
tescmd openclaw bridge [VIN] [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `VIN` | Vehicle identification number (positional) | Profile default |
| `--gateway URL` | Gateway WebSocket URL | `ws://127.0.0.1:18789` |
| `--token TOKEN` | Gateway auth token | `OPENCLAW_GATEWAY_TOKEN` env |
| `--config PATH` | Bridge config JSON file | `~/.config/tescmd/bridge.json` |
| `--port PORT` | Local telemetry server port | Random ephemeral port |
| `--fields PRESET` | Field preset: `default`, `driving`, `charging`, `climate`, `all` | `default` |
| `--interval SECONDS` | Override polling interval for all fields | Per-field defaults |
| `--dry-run` | Print events as JSONL, don't connect to gateway | Off |

## Configuration

### Config File

Create `~/.config/tescmd/bridge.json` to customize the bridge:

```json
{
  "gateway_url": "ws://127.0.0.1:18789",
  "gateway_token": "my-secret-token",
  "client_id": "node-host",
  "client_version": "0.1.0",
  "telemetry": {
    "Location": {"enabled": true, "granularity": 50.0, "throttle_seconds": 1.0},
    "Soc": {"enabled": true, "granularity": 5.0, "throttle_seconds": 10.0},
    "InsideTemp": {"enabled": true, "granularity": 5.0, "throttle_seconds": 30.0},
    "OutsideTemp": {"enabled": true, "granularity": 5.0, "throttle_seconds": 30.0},
    "VehicleSpeed": {"enabled": true, "granularity": 5.0, "throttle_seconds": 2.0},
    "ChargeState": {"enabled": true, "granularity": 0, "throttle_seconds": 0},
    "Locked": {"enabled": true, "granularity": 0, "throttle_seconds": 0}
  }
}
```

CLI flags (`--gateway`, `--token`) override config file values. The `OPENCLAW_GATEWAY_TOKEN` environment variable overrides the config file token.

### Default Filter Settings

| Field | Granularity | Throttle | Notes |
|-------|------------|----------|-------|
| `Location` | 50 meters | 1s | Haversine distance between coordinates |
| `Soc` | 5% | 10s | Battery state of charge |
| `InsideTemp` | 5 degrees | 30s | Cabin temperature |
| `OutsideTemp` | 5 degrees | 30s | Ambient temperature |
| `VehicleSpeed` | 5 mph | 2s | Current speed |
| `BatteryLevel` | 1% | 10s | Battery percentage |
| `EstBatteryRange` | 5 miles | 30s | Estimated range |
| `Odometer` | 1 mile | 60s | Odometer reading |
| `ChargeState` | any change | none | State field (Charging, Complete, etc.) |
| `DetailedChargeState` | any change | none | Detailed charge state |
| `Locked` | any change | none | Lock state |
| `SentryMode` | any change | none | Sentry mode on/off |
| `Gear` | any change | none | Drive gear (P, R, N, D) |

## Dual-Gate Filter

Every telemetry field passes through two independent gates. Both must pass for an event to be emitted:

1. **Delta gate** -- the value must have changed beyond the field's granularity threshold since the last emitted value. For location fields, this uses haversine distance in meters. For numeric fields, it's the absolute difference. For state fields (granularity=0), any value change passes.

2. **Throttle gate** -- enough time must have elapsed since the last emission for this field. A throttle of 0 means no time constraint.

The first value seen for any field always passes both gates.

### Disabling Fields

Set `"enabled": false` in the config to stop a field from emitting entirely:

```json
{
  "telemetry": {
    "Odometer": {"enabled": false, "granularity": 0, "throttle_seconds": 0}
  }
}
```

## Gateway Protocol

The bridge connects to the OpenClaw Gateway using the **node protocol** with Ed25519 device key signing:

### Handshake

1. Gateway sends `connect.challenge` event with a nonce
2. Bridge signs a pipe-delimited auth payload with its Ed25519 device key
3. Bridge sends `connect` request with role, scopes, client info, device identity, and auth token
4. Gateway responds with `hello-ok` on success

```json
{
  "type": "req",
  "id": "1",
  "method": "connect",
  "params": {
    "role": "node",
    "scopes": ["node.telemetry", "node.command"],
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": {
      "id": "node-host",
      "version": "tescmd/0.3.0",
      "platform": "tescmd",
      "deviceFamily": "darwin",
      "modelIdentifier": "tescmd",
      "mode": "node"
    },
    "device": {
      "id": "<sha256-of-public-key>",
      "publicKey": "<base64url-ed25519-public-key>",
      "signature": "<base64url-ed25519-signature>",
      "signedAt": 1706700000000,
      "nonce": "<challenge-nonce>"
    },
    "auth": {
      "token": "my-secret-token"
    }
  }
}
```

The device key is an Ed25519 keypair stored at `~/.config/tescmd/openclaw/device-key.pem` (auto-generated on first use). The signed payload format is: `v2|deviceId|clientId|mode|role|scopes|timestamp|token|nonce`.

### Events

After the handshake, events are sent as `req:agent` messages:

```json
{
  "method": "req:agent",
  "params": {
    "event_type": "location",
    "source": "node-host",
    "vin": "5YJ3E1EA1NF000000",
    "timestamp": "2026-01-31T10:30:00Z",
    "data": {
      "latitude": 37.3861,
      "longitude": -122.0839,
      "heading": 180,
      "speed": 0
    }
  }
}
```

### Reconnection

If the gateway connection drops, reconnection uses exponential backoff at two levels:

**Gateway level** (receive loop reconnect — handles WebSocket close/error):
- Base delay: 1 second, max: 60 seconds, factor: 2x, jitter: up to 10% of current interval

**Bridge level** (on_frame reconnect — handles disconnection during event sends):
- Base delay: 5 seconds, max: 120 seconds, factor: 2x

Events are silently dropped while disconnected. The bridge never crashes due to a send failure.

## Event Types

The emitter maps Tesla Fleet Telemetry fields to OpenClaw event types:

| Telemetry Field | Event Type | Data Fields |
|-----------------|------------|-------------|
| `Location` | `location` | `latitude`, `longitude`, `heading`, `speed` |
| `Soc` | `battery` | `battery_level` |
| `BatteryLevel` | `battery` | `battery_level` |
| `EstBatteryRange` | `battery` | `range_miles` |
| `InsideTemp` | `inside_temp` | `inside_temp_f` (converted to Fahrenheit) |
| `OutsideTemp` | `outside_temp` | `outside_temp_f` (converted to Fahrenheit) |
| `VehicleSpeed` | `speed` | `speed_mph` |
| `ChargeState` | `charge_started` / `charge_complete` / `charge_stopped` / `charge_state_changed` | `state` |
| `DetailedChargeState` | same as ChargeState | `state` |
| `Locked` | `security_changed` | `field`, `value` |
| `SentryMode` | `security_changed` | `field`, `value` |
| `Gear` | `gear_changed` | `gear` |

Unmapped telemetry fields are silently dropped.

> **Temperature units:** The emitter converts raw telemetry (Celsius) to Fahrenheit for outbound events (`inside_temp_f`, `outside_temp_f`). Read handlers (`temperature.get`) return Celsius (`inside_temp_c`, `outside_temp_c`) to match the Fleet API convention. Bots consuming both channels should be aware of this difference.

## Dry-Run Mode

Use `--dry-run` to test the filter pipeline without connecting to a gateway. Events are printed to stdout as one JSON object per line (JSONL):

```bash
tescmd openclaw bridge --dry-run --format json
```

This is useful for verifying filter configuration and seeing which events would be emitted.

## Architecture

The bridge is composed of four independent modules:

| Module | File | Responsibility |
|--------|------|----------------|
| `BridgeConfig` | `openclaw/config.py` | Load and merge config from file, CLI flags, env |
| `DualGateFilter` | `openclaw/filters.py` | Delta + throttle gating per field |
| `EventEmitter` | `openclaw/emitter.py` | Transform telemetry data to OpenClaw events |
| `GatewayClient` | `openclaw/gateway.py` | WebSocket connection, handshake, send, reconnect |
| `TelemetryBridge` | `openclaw/bridge.py` | Orchestrator wiring filter, emitter, gateway, and triggers |
| `CommandDispatcher` | `openclaw/dispatcher.py` | Inbound command handling (reads, writes, triggers, system.run) |
| `TelemetryStore` | `openclaw/telemetry_store.py` | In-memory cache of latest telemetry values |
| `TriggerManager` | `triggers/manager.py` | Trigger evaluation, cooldown, delivery |

The `TelemetryBridge.on_frame` method is passed as a callback to the telemetry server. For each frame, it iterates over the data, applies the filter, transforms passing data to events, and sends them to the gateway.

## Lifecycle Events

The bridge sends lifecycle events to the gateway at connection boundaries:

| Event Type | When | Purpose |
|---|---|---|
| `node.connected` | First telemetry frame received | Signals the node is live and streaming |
| `node.disconnecting` | Shutdown (Ctrl+C or graceful close) | Signals the node is leaving |

Lifecycle events use the standard `req:agent` envelope:

```json
{
  "method": "req:agent",
  "params": {
    "event_type": "node.connected",
    "source": "node-host",
    "vin": "5YJ3E1EA1NF000000",
    "timestamp": "2026-01-31T10:30:00Z",
    "data": {}
  }
}
```

In dry-run mode, lifecycle events are not sent.

## Bidirectional Command Dispatch

The bridge accepts inbound commands from bots via the gateway. When a bot sends a command (e.g. `door.lock`), the gateway forwards it to the node as a `node.invoke.request` event. The bridge's `CommandDispatcher` executes the command and sends the result back.

### Read Commands

Query cached telemetry state (no API call, instant response):

| Command | Returns |
|---|---|
| `location.get` | `latitude`, `longitude`, `heading`, `speed` |
| `battery.get` | `battery_level`, `range_miles` |
| `temperature.get` | `inside_temp_c`, `outside_temp_c` |
| `speed.get` | `speed_mph` |
| `charge_state.get` | `charge_state` |
| `security.get` | `locked`, `sentry_mode` |

### Write Commands

Execute vehicle commands via the Tesla Fleet API:

| Command | Parameters | Description |
|---|---|---|
| `door.lock` | -- | Lock vehicle doors |
| `door.unlock` | -- | Unlock vehicle doors |
| `climate.on` | -- | Start climate control |
| `climate.off` | -- | Stop climate control |
| `climate.set_temp` | `temp` (Fahrenheit) | Set cabin temperature |
| `charge.start` | -- | Start charging |
| `charge.stop` | -- | Stop charging |
| `charge.set_limit` | `percent` | Set charge limit |
| `trunk.open` | -- | Open rear trunk |
| `frunk.open` | -- | Open front trunk |
| `flash_lights` | -- | Flash vehicle lights |
| `honk_horn` | -- | Sound the horn |
| `sentry.on` | -- | Enable Sentry Mode |
| `sentry.off` | -- | Disable Sentry Mode |

Write commands enforce the same guards as the CLI: tier check (`readonly` tier blocks writes) and VCSEC signing requirement check.

### `system.run` Meta-Dispatch

The `system.run` command lets bots invoke any registered handler by name, useful when the bot doesn't match the exact OpenClaw command format:

```json
{
  "method": "system.run",
  "params": {
    "method": "door_lock",
    "params": {}
  }
}
```

Accepts both OpenClaw-style (`door.lock`) and API-style (`door_lock`) names via an alias table:

| API Name | OpenClaw Command |
|---|---|
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

## Trigger Subscription System

Triggers let bots register conditions on telemetry fields and get notified when they fire. Triggers are evaluated on every incoming telemetry frame, regardless of the dual-gate filter.

### Trigger Commands

| Command | Parameters | Description |
|---|---|---|
| `trigger.create` | `field`, `operator`, `value?`, `once?`, `cooldown_seconds?` | Create a trigger |
| `trigger.delete` | `id` | Delete a trigger |
| `trigger.list` | -- | List all triggers |
| `trigger.poll` | -- | Drain pending notifications |

### Convenience Aliases

These wrap `trigger.create` with a pre-filled field name:

| Command | Pre-filled Field | Example |
|---|---|---|
| `cabin_temp.trigger` | `InsideTemp` | `{operator: "gt", value: 100}` — cabin exceeds 100F |
| `outside_temp.trigger` | `OutsideTemp` | `{operator: "lt", value: 32}` — freezing outside |
| `battery.trigger` | `BatteryLevel` | `{operator: "lt", value: 20}` — battery low |
| `location.trigger` | `Location` | `{operator: "enter", value: {latitude, longitude, radius_m}}` |

### Operators

| Operator | Behavior | Example |
|---|---|---|
| `lt` | Numeric less than | `battery < 20` |
| `gt` | Numeric greater than | `speed > 80` |
| `lte` | Numeric less than or equal | `temp <= 32` |
| `gte` | Numeric greater than or equal | `temp >= 100` |
| `eq` | Exact match (string, bool, numeric) | `ChargeState == "Charging"` |
| `neq` | Not equal | `Gear != "P"` |
| `changed` | Value differs from previous | `Locked changed` (no threshold) |
| `enter` | Geofence: vehicle enters radius | See geofence below |
| `leave` | Geofence: vehicle leaves radius | See geofence below |

### Geofencing

Location triggers (`enter`/`leave`) operate on the `Location` field. The `value` is an object with `latitude`, `longitude`, and `radius_m`:

```json
{
  "field": "Location",
  "operator": "enter",
  "value": {"latitude": 37.7749, "longitude": -122.4194, "radius_m": 500}
}
```

Geofence triggers require a boundary crossing to fire -- being "already inside" a geofence on the first frame does not trigger an `enter` event. This prevents false positives on startup.

### Firing Modes

- **One-shot** (`once: true`): fires once, then auto-deletes
- **Persistent** (`once: false`, default): fires repeatedly with a `cooldown_seconds` delay between firings (default 60s)

### Notification Delivery

When a trigger fires, notifications are delivered through two channels:

1. **OpenClaw push** (gateway connected): a `trigger.fired` event is sent to the gateway:

```json
{
  "method": "req:agent",
  "params": {
    "event_type": "trigger.fired",
    "source": "node-host",
    "vin": "5YJ3E1EA1NF000000",
    "timestamp": "2026-01-31T10:30:00Z",
    "data": {
      "trigger_id": "a1b2c3d4e5f6",
      "field": "BatteryLevel",
      "operator": "lt",
      "threshold": 20,
      "value": 18,
      "previous_value": 21,
      "fired_at": "2026-01-31T10:30:00Z",
      "vin": "5YJ3E1EA1NF000000"
    }
  }
}
```

2. **MCP polling** (`trigger.poll`): notifications accumulate in a pending queue (max 500) and are returned/cleared when `trigger.poll` is called. This works even without a gateway connection.

### Example: Low Battery Alert

```json
{"method": "trigger.create", "params": {
  "field": "BatteryLevel",
  "operator": "lt",
  "value": 20,
  "once": true
}}
```

Response:

```json
{"id": "a1b2c3d4e5f6", "field": "BatteryLevel", "operator": "lt"}
```

### Limits

- Maximum 100 triggers per session
- Pending notification queue holds up to 500 entries (oldest dropped on overflow)
