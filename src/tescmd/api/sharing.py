"""Vehicle sharing API — driver management and invites."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tescmd.models.sharing import ShareDriverInfo, ShareInvite

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient


class SharingAPI:
    """Vehicle sharing operations (drivers and invites)."""

    def __init__(self, client: TeslaFleetClient) -> None:
        self._client = client

    async def add_driver(self, vin: str, *, email: str) -> ShareDriverInfo:
        """Add a driver by email."""
        data = await self._client.post(
            f"/api/1/vehicles/{vin}/drivers",
            json={"email": email},
        )
        return ShareDriverInfo.model_validate(data.get("response", {}))

    async def remove_driver(self, vin: str, *, share_user_id: int) -> dict[str, Any]:
        """Remove a driver by their share user ID."""
        data = await self._client.delete(
            f"/api/1/vehicles/{vin}/drivers",
            json={"share_user_id": share_user_id},
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def create_invite(self, vin: str) -> ShareInvite:
        """Create a vehicle share invite."""
        data = await self._client.post(f"/api/1/vehicles/{vin}/invitations")
        return ShareInvite.model_validate(data.get("response", {}))

    async def redeem_invite(self, *, code: str) -> ShareInvite:
        """Redeem a vehicle share invite code.

        This is an account-level endpoint (no VIN required) — the invite
        code itself encodes the vehicle association.
        """
        data = await self._client.post(
            "/api/1/invitations/redeem",
            json={"code": code},
        )
        return ShareInvite.model_validate(data.get("response", {}))

    async def revoke_invite(self, vin: str, *, invite_id: str) -> dict[str, Any]:
        """Revoke a vehicle share invite."""
        data = await self._client.post(
            f"/api/1/vehicles/{vin}/invitations/{invite_id}/revoke",
        )
        result: dict[str, Any] = data.get("response", {})
        return result

    async def list_invites(self, vin: str) -> list[ShareInvite]:
        """List active vehicle share invites."""
        data = await self._client.get(f"/api/1/vehicles/{vin}/invitations")
        raw_list: list[dict[str, Any]] = data.get("response", [])
        return [ShareInvite.model_validate(inv) for inv in raw_list]
