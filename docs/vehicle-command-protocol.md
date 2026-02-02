# Vehicle Command Protocol

Tesla's Vehicle Command Protocol requires commands to be cryptographically signed before the vehicle will execute them. tescmd implements this protocol transparently — once your key is enrolled, commands are signed automatically.

This document covers the protocol architecture, session management, and how tescmd routes commands.

## Overview

The protocol has three phases:

1. **Key enrollment** — register your EC public key on the vehicle (one-time, requires owner approval via Tesla app)
2. **ECDH session handshake** — establish a shared secret with the vehicle using Elliptic Curve Diffie-Hellman
3. **Command signing** — sign each command with HMAC-SHA256 using the session key, then send via the `signed_command` REST endpoint

```
Client                              Vehicle (via Fleet API)
  |                                       |
  |  1. Session handshake request         |
  |  (RoutableMessage + public key)       |
  |-------------------------------------->|
  |                                       |
  |  2. SessionInfo response              |
  |  (vehicle public key, epoch, counter) |
  |<--------------------------------------|
  |                                       |
  |  3. ECDH key derivation (both sides)  |
  |  shared_secret = ECDH(priv, peer_pub) |
  |  session_key = SHA1(shared_secret)[:16]
  |                                       |
  |  4. Signed command                    |
  |  (RoutableMessage + HMAC tag)         |
  |-------------------------------------->|
  |                                       |
  |  5. Command response                  |
  |<--------------------------------------|
```

## Key Enrollment

Before commands can be signed, the vehicle must trust your public key.

```bash
# Generate an EC P-256 key pair
tescmd key generate

# Open enrollment URL
tescmd key enroll
```

The enrollment flow:

1. `tescmd key enroll` opens `https://tesla.com/_ak/<domain>` on your phone
2. You tap "Finish Setup" on the web page
3. The Tesla app shows an "Add Virtual Key" prompt — approve it
4. The key is now trusted for command signing

You can verify your enrolled key under Tesla app > Profile > Security & Privacy > Third-Party Apps.

## Session Management

Sessions are managed per (VIN, domain) pair. The two command domains are:

| Domain | Commands | Examples |
|---|---|---|
| **VCSEC** (Vehicle Security) | Lock, unlock, trunk, windows, remote start, key enrollment | `door_lock`, `door_unlock`, `actuate_trunk` |
| **Infotainment** | Charge, climate, media, navigation, software, sentry | `charge_start`, `set_temps`, `honk_horn` |

### Handshake

1. Build a `RoutableMessage` with a `SessionInfoRequest` containing the client's 65-byte uncompressed EC public key
2. POST to `/api/1/vehicles/{vin}/signed_command` with the base64-encoded protobuf
3. Parse the vehicle's `SessionInfo` response: vehicle public key, epoch, counter, clock time
4. Derive session key: `shared_secret = ECDH(client_priv, vehicle_pub)`, then `K = SHA1(shared_secret)[:16]`
5. Derive sub-keys: `signing_key = HMAC-SHA256(K, "authenticated command")`, `session_info_key = HMAC-SHA256(K, "session info")`

### Session Caching

Sessions are cached in memory with a 5-minute TTL. Each session tracks:

- **Shared key** — the 16-byte derived session key
- **Signing key** — HMAC-derived key for command authentication
- **Epoch** — session identifier from the vehicle
- **Counter** — monotonically increasing anti-replay counter
- **Clock offset** — difference between vehicle clock and local clock

Expired sessions trigger an automatic re-handshake.

## Command Signing

For each command:

1. **Serialize metadata** as TLV (tag-length-value): signature type, domain, VIN (personalization), epoch, expiry timestamp, counter, and optional flags — tags must appear in ascending order (see [TLV tag table](#tlv-metadata-encoding) below)
2. **Build payload** — the command body as serialized protobuf bytes (VCSEC commands use `UnsignedMessage`, Infotainment commands use `Action { VehicleAction { ... } }`)
3. **Compute HMAC tag**: `HMAC-SHA256(signing_key, metadata || 0xFF || payload)` — the `0xFF` byte (TAG_END) separates metadata from payload in the HMAC input
   - VCSEC domain: truncate to 17 bytes
   - Infotainment domain: full 32 bytes
4. **Assemble RoutableMessage** with the payload, signature data (epoch, counter, expiry, tag), and signer identity (public key)
5. **Serialize and base64-encode** the RoutableMessage
6. **POST** to `/api/1/vehicles/{vin}/signed_command`

## Command Routing

tescmd maintains a registry of all known commands with their domain and signing requirements:

| Category | Count | Domain | Signed |
|---|---|---|---|
| VCSEC commands | 8 | `DOMAIN_VEHICLE_SECURITY` | Yes |
| Infotainment commands | 67 | `DOMAIN_INFOTAINMENT` | Yes |
| Unsigned commands | 4 | `DOMAIN_BROADCAST` | No (`wake_up` + 3 managed charging) |

The `command_protocol` setting controls how commands are routed:

```
command_protocol = "auto" (default)

  Has enrolled keys + full tier?
    Yes → SignedCommandAPI
      Command in registry + requires_signing?
        Yes → ECDH session + HMAC → POST /signed_command
        No  → Legacy REST → POST /command/{name}
    No  → CommandAPI (legacy REST for everything)
```

## Module Structure

```
src/tescmd/protocol/
├── __init__.py           # Re-exports: Session, SessionManager, CommandSpec, etc.
├── protobuf/
│   ├── __init__.py
│   └── messages.py       # Hand-written protobuf: RoutableMessage, SessionInfo, Domain, etc.
├── session.py            # SessionManager — ECDH handshake, caching, counter management
├── signer.py             # HMAC-SHA256 signing, session info tag verification
├── metadata.py           # TLV serialization for command metadata (all 8 tags + end sentinel)
├── payloads.py           # Protobuf payload builders for each command (VCSEC UnsignedMessage, Infotainment Action)
├── commands.py           # Command registry: name → (domain, signing requirement)
└── encoder.py            # RoutableMessage assembly + base64 encoding

src/tescmd/crypto/
├── keys.py               # EC key generation, PEM load/save
├── ecdh.py               # ECDH key exchange, uncompressed public key extraction
└── schnorr.py            # Schnorr signatures (Tesla.SS256) for fleet telemetry JWS tokens

src/tescmd/api/
└── signed_command.py     # SignedCommandAPI — routes signed/unsigned commands
```

## Implementation Notes

The Vehicle Command Protocol has several subtleties that aren't documented in Tesla's official sources. These were discovered through debugging against a live vehicle.

### TLV Metadata Encoding

The metadata block is a sequence of TLV (tag-length-value) entries: `tag(1B) || length(1B) || value`. Tags must appear in ascending order. The complete tag table (from Tesla's `signatures.proto` Tag enum):

| Tag | Name | Size | Description |
|---|---|---|---|
| `0x00` | `TAG_SIGNATURE_TYPE` | 1 byte | SignatureType enum (8 = HMAC_PERSONALIZED) |
| `0x01` | `TAG_DOMAIN` | 1 byte | Numeric Domain enum value (e.g., 2 = VCSEC, 3 = Infotainment) |
| `0x02` | `TAG_PERSONALIZATION` | variable | VIN string (17 chars) |
| `0x03` | `TAG_EPOCH` | variable | Session epoch identifier from vehicle |
| `0x04` | `TAG_EXPIRES_AT` | 4 bytes | Big-endian uint32 — seconds since Unix epoch |
| `0x05` | `TAG_COUNTER` | 4 bytes | Big-endian uint32 — monotonic anti-replay counter |
| `0x06` | `TAG_CHALLENGE` | variable | BLE challenge (not used for REST path) |
| `0x07` | `TAG_FLAGS` | 4 bytes | Big-endian uint32 — optional flags |
| `0xFF` | `TAG_END` | 0 bytes | Bare byte — terminates metadata (no length byte) |

The domain tag value is a numeric enum, not a string. The end sentinel (`TAG_END = 0xFF`) is a bare byte with no length field — it serves as the separator between metadata and payload in the HMAC input (see below).

### Expiry Timestamps

The `expires_at` field in command metadata is **vehicle epoch-relative**, not an absolute Unix timestamp. The vehicle starts its epoch counter at boot and sends its clock time in the `SessionInfo` handshake response. The client computes:

```
clock_offset = vehicle_clock_time - local_unix_time
expires_at = local_unix_time + clock_offset + ttl_seconds
```

This yields a small value (typically thousands of seconds) relative to the vehicle's epoch, not the billions-range Unix timestamp. Getting this wrong causes `ERROR_SIGNATURE_MISMATCH` because the vehicle's HMAC computation uses the epoch-relative time.

### HMAC Input

The HMAC tag is computed over `metadata_bytes || 0xFF || payload_bytes`. The `0xFF` byte (TAG_END) is a bare separator between the TLV metadata block and the protobuf payload — it has no length byte. This matches the Go SDK's `Checksum()` method which writes `byte(signatures.Tag_TAG_END)` between streaming the metadata entries and the message bytes.

For VCSEC commands, the resulting tag is truncated to 17 bytes; for Infotainment commands, the full 32-byte tag is used.

### Session Info Verification

After receiving a `SessionInfo` response, the client verifies the HMAC tag attached to the response using a derived session info key: `HMAC-SHA256(K, "session info")`. This prevents man-in-the-middle injection of fake session parameters. The `verify_session_info_tag()` function in `signer.py` handles this check.

### Session Handshake

The handshake exchanges uncompressed 65-byte EC P-256 public keys (prefix byte `0x04`). The client sends its key in a `SessionInfoRequest`; the vehicle responds with a `SessionInfo` containing the vehicle's public key, epoch, counter, and clock time. If a cached session becomes stale (e.g., the vehicle reboots and assigns a new epoch), the command will fail with a signature error. The `SessionManager` detects this and automatically triggers a re-handshake before retrying.

### Payload Building

Command payloads are serialized as protobuf, not JSON. The `payloads.py` module contains builders for each command:

- **VCSEC commands** produce a serialized `UnsignedMessage` (e.g., `RKEAction` for lock/unlock, `ClosureMoveRequest` for trunk)
- **Infotainment commands** produce a serialized `Action { VehicleAction { ... } }` wrapping command-specific sub-messages

Field numbers match Tesla's `car_server.proto` and `vcsec.proto` definitions. The `build_command_payload()` function dispatches to the correct builder based on the REST command name.

## Troubleshooting

**"Key not enrolled"** — Run `tescmd key enroll <VIN>` and approve in the Tesla app.

**"Session handshake failed"** — The vehicle may be asleep or unreachable. Wake it first with `tescmd vehicle wake --wake`.

**"command_protocol is 'signed' but no key pair found"** — Generate keys with `tescmd key generate` and run `tescmd setup` to configure full tier.

**Force unsigned for debugging** — Set `TESLA_COMMAND_PROTOCOL=unsigned` or use `command_protocol = "unsigned"` in config.

## References

- [Tesla Vehicle Command Protocol](https://github.com/teslamotors/vehicle-command) — official Go implementation and proto definitions
- [Tesla Fleet API — Billing and Limits](https://developer.tesla.com/docs/fleet-api/billing-and-limits) — API pricing and rate limits
- [Tesla Fleet API — signed_command endpoint](https://developer.tesla.com/docs/fleet-api) — API documentation
