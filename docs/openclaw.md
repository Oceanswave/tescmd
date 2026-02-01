# OpenClaw Bridge

The OpenClaw bridge streams filtered vehicle telemetry to an [OpenClaw](https://openclaw.ai/) Gateway, enabling real-time agent consumption of vehicle state. Unlike raw telemetry streaming, the bridge applies dual-gate filtering (delta threshold + throttle interval) to reduce noise and control event volume.

## Quick Start

```bash
# Bridge to local gateway (default: ws://127.0.0.1:18789)
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
  "client_id": "tescmd-bridge",
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

The bridge connects to the OpenClaw Gateway using the operator protocol:

### Handshake

1. Gateway sends `connect.challenge` with a nonce
2. Bridge sends `connect` with operator role, scopes, client info, and auth token
3. Gateway responds with `hello-ok` on success

```json
{"method": "connect", "params": {
  "role": "operator",
  "scopes": ["operator.send"],
  "client_id": "tescmd-bridge",
  "client_version": "0.1.0",
  "nonce": "abc123",
  "token": "my-secret-token"
}}
```

### Events

After the handshake, events are sent as `req:agent` messages:

```json
{
  "method": "req:agent",
  "params": {
    "event_type": "location",
    "source": "tescmd-bridge",
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

If the gateway connection drops, the bridge reconnects with exponential backoff:

- Base delay: 1 second
- Max delay: 60 seconds
- Factor: 2x per attempt
- Jitter: 10% of current delay

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
| `ChargeState` | `charge_started` / `charge_complete` / `charge_stopped` | `state` |
| `DetailedChargeState` | same as ChargeState | `state` |
| `Locked` | `security_changed` | `field`, `value` |
| `SentryMode` | `security_changed` | `field`, `value` |
| `Gear` | `gear_changed` | `gear` |

Unmapped telemetry fields are silently dropped.

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
| `TelemetryBridge` | `openclaw/bridge.py` | Orchestrator wiring filter, emitter, and gateway |

The `TelemetryBridge.on_frame` method is passed as a callback to the telemetry server. For each frame, it iterates over the data, applies the filter, transforms passing data to events, and sends them to the gateway.
