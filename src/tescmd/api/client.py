"""Async HTTP client for the Tesla Fleet API."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from tescmd.api.errors import (
    AuthError,
    MissingScopesError,
    NetworkError,
    RateLimitError,
    RegistrationRequiredError,
    TeslaAPIError,
    VehicleAsleepError,
)

# ---------------------------------------------------------------------------
# Region -> base URL mapping
# ---------------------------------------------------------------------------

REGION_BASE_URLS: dict[str, str] = {
    "na": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    "eu": "https://fleet-api.prd.eu.vn.cloud.tesla.com",
    "cn": "https://fleet-api.prd.cn.vn.cloud.tesla.com",
}

# ---------------------------------------------------------------------------
# Tesla Fleet API documented rate limits (per device, per account).
# See: https://developer.tesla.com/docs/fleet-api/billing-and-limits
# ---------------------------------------------------------------------------

RATE_LIMITS = {
    "data": 60,  # Realtime data: 60 req/min
    "commands": 30,  # Device commands: 30 req/min
    "wakes": 3,  # Wakes: 3 req/min
    "auth": 20,  # Auth: 20 req/sec
}
_RATE_LIMIT_MAX_RETRIES = 3


class TeslaFleetClient:
    """Low-level async HTTP client for Tesla Fleet API endpoints."""

    def __init__(
        self,
        access_token: str,
        region: str = "na",
        timeout: float = 30.0,
        on_token_refresh: Callable[[], Awaitable[str | None]] | None = None,
        on_rate_limit_wait: Callable[[int, int, int], Awaitable[None]] | None = None,
    ) -> None:
        base_url = REGION_BASE_URLS.get(region)
        if base_url is None:
            msg = f"Unknown region {region!r}; expected one of {sorted(REGION_BASE_URLS)}"
            raise ValueError(msg)

        self._access_token = access_token
        self._on_token_refresh = on_token_refresh
        self._on_rate_limit_wait = on_rate_limit_wait
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    # -- public helpers -----------------------------------------------------

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Issue a GET request and return the parsed JSON body."""
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Issue a POST request and return the parsed JSON body."""
        return await self._request("POST", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """Issue a DELETE request and return the parsed JSON body."""
        return await self._request("DELETE", path, **kwargs)

    def update_token(self, access_token: str) -> None:
        """Replace the current access token and update the header."""
        self._access_token = access_token
        self._client.headers["Authorization"] = f"Bearer {access_token}"

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # -- async context manager -----------------------------------------------

    async def __aenter__(self) -> TeslaFleetClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()

    # -- internal ------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Issue an HTTP request with automatic retry on 429 rate-limit responses."""
        for attempt in range(_RATE_LIMIT_MAX_RETRIES + 1):
            try:
                return await self._send(method, path, **kwargs)
            except RateLimitError as exc:
                if attempt >= _RATE_LIMIT_MAX_RETRIES:
                    raise
                wait = exc.retry_after or min(2 ** (attempt + 1), 30)
                if self._on_rate_limit_wait:
                    await self._on_rate_limit_wait(wait, attempt + 1, _RATE_LIMIT_MAX_RETRIES)
                else:
                    await asyncio.sleep(wait)
        raise RateLimitError()  # unreachable, satisfies type checker

    async def _send(
        self,
        method: str,
        path: str,
        *,
        _retried: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a single HTTP request, handling auth refresh on 401."""
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise NetworkError(f"Request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise NetworkError(f"Connection error: {exc}") from exc

        # Handle 401 with optional token refresh
        if response.status_code == 401 and not _retried:
            if self._on_token_refresh is not None:
                new_token = await self._on_token_refresh()
                if new_token is not None:
                    self.update_token(new_token)
                    return await self._send(method, path, _retried=True, **kwargs)
            raise AuthError("Authentication failed", status_code=401)

        return self._parse_response(response)

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        """Translate HTTP status codes to domain exceptions and return JSON."""
        if response.status_code == 429:
            raw = response.headers.get("retry-after")
            retry_after: int | None = None
            if raw is not None:
                try:
                    retry_after = int(raw)
                except ValueError:
                    retry_after = 30  # Fallback for HTTP-date strings
            raise RateLimitError(retry_after=retry_after)

        if response.status_code == 408:
            raise VehicleAsleepError("Vehicle is asleep", status_code=408)

        if response.status_code == 412:
            raise RegistrationRequiredError(
                "Your application is not registered with the Tesla Fleet API "
                "for this region. Run 'tescmd auth register' to fix this.",
                status_code=412,
            )

        if response.status_code == 403:
            text = response.text[:200]
            if "missing scopes" in text.lower():
                raise MissingScopesError(text, status_code=403)
            raise AuthError(f"HTTP 403: {text}", status_code=403)

        if response.status_code >= 400:
            text = response.text[:200]
            raise TeslaAPIError(
                f"HTTP {response.status_code}: {text}",
                status_code=response.status_code,
            )

        # 204 No Content — return empty dict (no body to parse)
        if response.status_code == 204:
            return {}

        try:
            result: dict[str, Any] = response.json()
        except json.JSONDecodeError as exc:
            raise TeslaAPIError(
                f"Invalid JSON response: {response.text[:200]}",
                status_code=response.status_code,
            ) from exc
        return result
