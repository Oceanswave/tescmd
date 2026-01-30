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
