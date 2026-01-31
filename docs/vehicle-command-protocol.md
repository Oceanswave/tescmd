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

1. **Serialize metadata** as TLV (tag-length-value): epoch, expiry timestamp, counter
2. **Build payload** — the command body as JSON-encoded bytes
3. **Compute HMAC tag**: `HMAC-SHA256(signing_key, metadata || payload)`
   - VCSEC domain: truncate to 17 bytes
   - Infotainment domain: full 32 bytes
4. **Assemble RoutableMessage** with the payload, signature data (epoch, counter, expiry, tag), and signer identity (public key)
5. **Serialize and base64-encode** the RoutableMessage
6. **POST** to `/api/1/vehicles/{vin}/signed_command`

## Command Routing

tescmd maintains a registry of all known commands with their domain and signing requirements:

| Category | Count | Domain | Signed |
|---|---|---|---|
| VCSEC commands | 7 | `DOMAIN_VEHICLE_SECURITY` | Yes |
| Infotainment commands | ~45 | `DOMAIN_INFOTAINMENT` | Yes |
| Unsigned commands | 1 (`wake_up`) | `DOMAIN_BROADCAST` | No |

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
├── signer.py             # HMAC-SHA256 signing and verification
├── metadata.py           # TLV serialization for command metadata
├── commands.py           # Command registry: name → (domain, signing requirement)
└── encoder.py            # RoutableMessage assembly + base64 encoding

src/tescmd/crypto/
├── keys.py               # EC key generation, PEM load/save
└── ecdh.py               # ECDH key exchange, uncompressed public key extraction

src/tescmd/api/
└── signed_command.py     # SignedCommandAPI — routes signed/unsigned commands
```

## Implementation Notes

The Vehicle Command Protocol has several subtleties that aren't documented in Tesla's official sources. These were discovered through debugging against a live vehicle.

### TLV Metadata Encoding

The metadata TLV (tag-length-value) format uses single-byte tags. The domain tag (`TAG_DOMAIN = 0x05`) must be encoded as a single byte value (e.g., `0x01` for Infotainment), not as a string. The end sentinel (`TAG_END = 0xFF`) is a bare byte — not a full TLV triple.

### Expiry Timestamps

The `expires_at` field in command metadata is **vehicle epoch-relative**, not an absolute Unix timestamp. The vehicle starts its epoch counter at boot and sends its clock time in the `SessionInfo` handshake response. The client computes:

```
clock_offset = vehicle_clock_time - local_unix_time
expires_at = local_unix_time + clock_offset + ttl_seconds
```

This yields a small value (typically thousands of seconds) relative to the vehicle's epoch, not the billions-range Unix timestamp. Getting this wrong causes `ERROR_SIGNATURE_MISMATCH` because the vehicle's HMAC computation uses the epoch-relative time.

### HMAC Input

The HMAC tag is computed over `metadata_bytes || payload_bytes`. For VCSEC commands, the tag is truncated to 17 bytes; for Infotainment commands, the full 32-byte tag is used.

### Session Handshake

The handshake exchanges uncompressed 65-byte EC P-256 public keys (prefix byte `0x04`). The client sends its key in a `SessionInfoRequest`; the vehicle responds with a `SessionInfo` containing the vehicle's public key, epoch, counter, and clock time.

## Troubleshooting

**"Key not enrolled"** — Run `tescmd key enroll <VIN>` and approve in the Tesla app.

**"Session handshake failed"** — The vehicle may be asleep or unreachable. Wake it first with `tescmd vehicle wake --wake`.

**"command_protocol is 'signed' but no key pair found"** — Generate keys with `tescmd key generate` and run `tescmd setup` to configure full tier.

**Force unsigned for debugging** — Set `TESLA_COMMAND_PROTOCOL=unsigned` or use `command_protocol = "unsigned"` in config.

## References

- [Tesla Vehicle Command Protocol](https://github.com/teslamotors/vehicle-command) — official Go implementation and proto definitions
- [Tesla Fleet API — Billing and Limits](https://developer.tesla.com/docs/fleet-api/billing-and-limits) — API pricing and rate limits
- [Tesla Fleet API — signed_command endpoint](https://developer.tesla.com/docs/fleet-api) — API documentation
