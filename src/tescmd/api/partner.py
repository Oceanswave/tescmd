"""Partner account API — public key retrieval and fleet telemetry errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class PartnerAPI:
    """Partner-level endpoints (require partner token, not user token)."""

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def public_key(self, *, domain: str) -> dict[str, Any]:
        """Get the public key registered for *domain*."""
        data = await self._client.get(
            "/api/1/partner_accounts/public_key",
            params={"domain": domain},
        )
        result: dict[str, Any] = data.get("response", data)
        return result

    async def fleet_telemetry_error_vins(self) -> list[str]:
        """List VINs that have recent fleet telemetry errors."""
        data = await self._client.get(
            "/api/1/partner_accounts/fleet_telemetry_error_vins",
        )
        result: list[str] = data.get("response", [])
        return result

    async def fleet_telemetry_errors(self) -> list[dict[str, Any]]:
        """Get recent fleet telemetry errors across all vehicles."""
        data = await self._client.get(
            "/api/1/partner_accounts/fleet_telemetry_errors",
        )
        result: list[dict[str, Any]] = data.get("response", [])
        return result
