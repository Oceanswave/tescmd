"""Cache key generation for response cache entries."""

from __future__ import annotations

import hashlib


def cache_key(vin: str, endpoints: list[str] | None = None) -> str:
    """Return a filesystem-safe cache key for *vin* and optional *endpoints*.

    * No endpoints → ``"{vin}_all"``
    * With endpoints → ``"{vin}_{sha256(sorted_semicolon_joined)[:12]}"``

    Sorting ensures order-independence: ``["a","b"]`` and ``["b","a"]``
    produce the same key.
    """
    if not endpoints:
        return f"{vin}_all"
    joined = ";".join(sorted(endpoints))
    digest = hashlib.sha256(joined.encode()).hexdigest()[:12]
    return f"{vin}_{digest}"


def generic_cache_key(
    scope: str,
    identifier: str,
    endpoint: str,
    params: dict[str, str] | None = None,
) -> str:
    """Return a filesystem-safe cache key for any API endpoint.

    Key format: ``{scope}_{identifier}_{sha256(endpoint+sorted_params)[:12]}``

    *scope* categorises the entry (``"vin"``, ``"site"``, ``"account"``,
    ``"partner"``).  *identifier* disambiguates within the scope (a VIN,
    site-id, or ``"global"``).  *endpoint* names the API call.  Optional
    *params* are hashed into the key so different query parameters produce
    different cache entries.

    Examples::

        generic_cache_key("account", "global", "vehicle.list")
        generic_cache_key("vin", "5YJ3E...", "nearby_chargers")
        generic_cache_key("site", "12345", "site_info")
    """
    parts = endpoint
    if params:
        sorted_params = ";".join(f"{k}={v}" for k, v in sorted(params.items()))
        parts = f"{endpoint};{sorted_params}"
    digest = hashlib.sha256(parts.encode()).hexdigest()[:12]
    return f"{scope}_{identifier}_{digest}"
