# Tesla Fleet API Costs & How tescmd Reduces Them

Tesla's Fleet API uses a pay-per-use billing model. Every request that returns a status code below 500 is billable. This document explains the billing model, the most expensive operations, and how tescmd's built-in cost protections work.

## Fleet API Billing Model

- **Pay-per-use** — charges accumulate per request, rounded to the nearest $0.01
- **Monthly billing cycle** — starts on the 1st; invoice due at month-end; auto-charged 14 days later
- **$10 monthly discount** — covers basic use for a few vehicles (scheduled to be removed September 1, 2025)
- **Billing limit** — defaults to $0 until a payment method is added; alert at 80% of limit; API suspended if exceeded
- **All non-5xx responses are billable** — including 4xx errors (auth failures, rate limits, vehicle asleep)

Each endpoint has a pricing category listed in the [Fleet API docs](https://developer.tesla.com/docs/fleet-api). Costs vary by category — wake and vehicle data endpoints are among the most expensive.

## Rate Limits

Per device, per account:

| Category | Limit |
|---|---|
| Realtime Data | 60 requests/min |
| Device Commands | 30 requests/min |
| Wakes | 3 requests/min |

Exceeding rate limits returns HTTP 429 with a `retry_after` value.

## What Makes the API Expensive

### Polling `vehicle_data`

The `vehicle_data` endpoint returns the full vehicle state snapshot. Tesla's own docs warn that it should not be polled regularly. At roughly $1 per 500 requests, polling once per minute for a month costs approximately $85 per vehicle — not counting wakes.

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

  [W] Wake via API    [C] Cancel
```

- **W** — Send the billable wake request
- **C** — Abort. Wake from the Tesla app instead (free), then retry

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

### Cost Savings in Practice

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

4. **Monitor your usage.** The Tesla Developer Portal shows your billing. Set a billing limit as a safety net.

5. **Consider Fleet Telemetry** for continuous monitoring. Tesla's streaming protocol costs roughly $0.007/hour per vehicle — orders of magnitude cheaper than polling `vehicle_data`.

## References

- [Tesla Fleet API — Billing and Limits](https://developer.tesla.com/docs/fleet-api/billing-and-limits)
- [Tesla Developer Portal](https://developer.tesla.com/)
