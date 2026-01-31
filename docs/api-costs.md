# Tesla Fleet API Costs & How tescmd Reduces Them

Tesla's Fleet API uses a pay-per-use billing model. Every request that returns a status code below 500 is billable — including 4xx errors like "vehicle asleep" (408) and rate limit responses (429). This document explains the billing model, shows real cost examples, and explains how tescmd's built-in cost protections work.

> **Official reference:** [Tesla Fleet API — Billing and Limits](https://developer.tesla.com/docs/fleet-api/billing-and-limits)

## Fleet API Billing Model

- **Pay-per-use** — charges accumulate per request; each endpoint has a pricing tier
- **Monthly billing cycle** — starts on the 1st; invoice due at month-end; auto-charged 14 days later
- **$10 monthly credit** — covers basic use for a few vehicles (Tesla has announced this credit will be removed)
- **Billing limit** — defaults to $0 until a payment method is added; alert at 80% of limit; API access suspended if exceeded
- **All non-5xx responses are billable** — including 401 (auth failure), 408 (vehicle asleep), 429 (rate limit)

## Pricing Tiers

Tesla groups endpoints into pricing tiers. The exact per-request cost varies by tier, but the relative cost ordering is:

| Tier | Example Endpoints | Relative Cost |
|---|---|---|
| Wake | `wake_up` | Highest |
| Vehicle Data | `vehicle_data`, `vehicle_data_combo` | High |
| Vehicle Commands | `command/*`, `signed_command` | Medium |
| Vehicle State | `vehicle` (basic info) | Lower |
| User/Fleet | `me`, `region`, `vehicles` | Lowest |

Current pricing is published on [Tesla's billing page](https://developer.tesla.com/docs/fleet-api/billing-and-limits). Check there for exact per-request costs — they may change.

## Rate Limits

Per device, per account:

| Category | Limit |
|---|---|
| Realtime Data | 60 requests/min |
| Device Commands | 30 requests/min |
| Wakes | 3 requests/min |

Exceeding rate limits returns HTTP 429 with a `retry_after` value. The 429 response itself is billable.

## Cost Examples

### Example 1: Simple battery check

Without tescmd (naive script):

| Step | Request | Billable? | Notes |
|---|---|---|---|
| 1 | `GET vehicle_data` | Yes | Vehicle is asleep → 408 |
| 2 | `POST wake_up` | Yes | Most expensive tier |
| 3 | `GET vehicle_data` (poll) | Yes | Still waking → 408 |
| 4 | `POST wake_up` (retry) | Yes | Rate limit risk |
| 5 | `GET vehicle_data` | Yes | Finally succeeds |

**Result:** 5 billable requests for one battery check.

With tescmd:

| Step | What happens | Billable? |
|---|---|---|
| 1 | Check cache → miss | No |
| 2 | Check wake state cache → miss | No |
| 3 | Prompt user: "Vehicle is asleep. Wake via API?" | No |
| 4 | User wakes via Tesla app (free) and hits [R] Retry | No |
| 5 | `GET vehicle_data` → success, cached | Yes (1 request) |

**Result:** 1 billable request. Subsequent checks within 60s: 0 requests.

### Example 2: Monitoring script (every 5 minutes)

Without tescmd: 288 checks/day × 4-5 requests each = **1,000-1,400 billable requests/day**.

With tescmd (`--wake` flag, vehicle stays awake):
- First check: 1 wake + 1 data = 2 requests
- Subsequent checks within 60s TTL: 0 requests (cache hit)
- Checks after TTL but vehicle still awake: 1 request each (wake state cached)
- **Result: ~250 requests/day** (70-80% reduction)

With tescmd + cache TTL tuned to 300s: **~50 requests/day** (95% reduction).

### Example 3: Fleet Telemetry vs. Polling

For continuous vehicle monitoring, Tesla's Fleet Telemetry streaming is dramatically cheaper:

| Approach | Daily Cost (approx.) | Requests/day |
|---|---|---|
| Poll `vehicle_data` every minute (naive) | High | ~1,400+ |
| tescmd with cache (5-min TTL, `--wake`) | Moderate | ~250 |
| Fleet Telemetry streaming | Very low | 0 (streaming) |

Fleet Telemetry pushes data to your server over a persistent connection — no polling needed. The setup wizard (`tescmd setup`) highlights this option and links to Tesla's Fleet Telemetry documentation.

## What Makes the API Expensive

### Polling `vehicle_data`

The `vehicle_data` endpoint returns the full vehicle state snapshot. Tesla's own docs warn that it should not be polled regularly. Polling once per minute for a month generates ~43,000 requests per vehicle — a significant cost.

### Wake Requests

Wake is the most expensive category. If the vehicle is asleep, every data query or command requires a wake first. Wake requests:

- Are rate-limited to 3/min
- Are billable even if the vehicle doesn't wake in time
- Are completely free when initiated from the Tesla mobile app (iOS/Android)

### Invisible Cost Multipliers

Without protections, a simple script that checks battery every 5 minutes would:

1. Attempt to read vehicle data → vehicle is asleep → billable 408 response
2. Send a wake request → billable
3. Poll for wake completion → potentially multiple billable requests
4. Read vehicle data again → billable

That's 4+ billable requests for a single battery check. Multiply by 288 checks/day = 1,000+ billable requests per day from a seemingly harmless cron job.

## How tescmd Reduces Costs

tescmd implements a three-layer defense against unnecessary API spending:

### 1. Response Cache (Disk-Based)

Every API response is cached as a JSON file under `~/.cache/tescmd/` with a configurable TTL (default: 60 seconds). Repeated queries within the TTL window return instantly from disk with zero API calls.

```bash
# First call: hits API, caches response
tescmd charge status

# Second call within 60s: instant cache hit, no API call
tescmd charge status

# Force fresh data when needed
tescmd charge status --fresh
```

**Cache invalidation:** Write-commands (`charge start`, `climate on`, `security lock`, etc.) automatically clear the cache after success, so subsequent reads reflect the new state.

**Configuration:**

| Variable | Default | Description |
|---|---|---|
| `TESLA_CACHE_ENABLED` | `true` | Enable/disable cache |
| `TESLA_CACHE_TTL` | `60` | Cache lifetime in seconds |
| `TESLA_CACHE_DIR` | `~/.cache/tescmd` | Cache directory |

### 2. Wake State Cache

A separate short-lived cache (30s TTL) tracks whether the vehicle was recently confirmed online. If the vehicle was online 20 seconds ago, tescmd skips the wake attempt entirely and goes straight to the data request.

This avoids the most common waste pattern: sending a billable wake request for a vehicle that's already awake.

### 3. Wake Confirmation Prompt

By default, tescmd will not send a billable wake API call without asking first.

**Interactive mode (TTY):**

```
Vehicle is asleep.

  Waking via the Tesla app (iOS/Android) is free.
  Sending a wake via the API is billable.

  [W] Wake via API    [R] Retry    [C] Cancel
```

- **W** — Send the billable wake request
- **R** — Retry the command (user wakes via Tesla app first, which is free)
- **C** — Abort

**JSON / piped mode:** Returns a structured error with guidance:

```json
{
  "ok": false,
  "error": {
    "code": "vehicle_asleep",
    "message": "Vehicle is asleep. Use --wake to send a billable wake via the API, or wake from the Tesla app for free."
  }
}
```

**Opt-in auto-wake for scripts:**

```bash
# Skip the prompt — accept the cost
tescmd charge status --wake
```

The `--wake` flag is an explicit opt-in. Scripts and agents that include it are acknowledging the cost. Scripts that omit it are protected from surprise charges.

### Cost Savings Summary

| Scenario | Without tescmd | With tescmd |
|---|---|---|
| Check battery 10 times in a minute | 10 API calls (+ wakes) | 1 API call + 9 cache hits |
| Agent checks status, then starts charging | 2 data calls + 2 wakes | 1 data call + 1 command (wake cached) |
| Script runs charge status in a loop | Unbounded API calls | 1 call per TTL window |
| Vehicle is asleep, user just wants to check | Billable wake sent silently | Prompt first, suggest free Tesla app wake |

## Recommendations for Users

1. **Use the Tesla app to wake your vehicle** before running tescmd commands. Waking from the app is free; waking via the API is billable.

2. **Let the cache work.** Default 60s TTL means rapid-fire queries cost nothing. Only use `--fresh` when you need real-time data.

3. **Use `--wake` intentionally.** Only add it to scripts where you've accepted the cost. Never use it in tight loops.

4. **Monitor your usage.** The [Tesla Developer Portal](https://developer.tesla.com/) shows your billing. Set a billing limit as a safety net.

5. **Consider Fleet Telemetry** for continuous monitoring. Tesla's streaming protocol is orders of magnitude cheaper than polling `vehicle_data`. The setup wizard (`tescmd setup`) provides guidance on this option.

6. **Tune cache TTL for your use case.** If you only need data every few minutes, increase `TESLA_CACHE_TTL` to 300 or more.

## References

- [Tesla Fleet API — Billing and Limits](https://developer.tesla.com/docs/fleet-api/billing-and-limits) — official pricing, rate limits, and billing details
- [Tesla Developer Portal](https://developer.tesla.com/) — manage your application, view usage, and set billing limits
- [Tesla Fleet Telemetry](https://github.com/teslamotors/fleet-telemetry) — streaming alternative to polling
