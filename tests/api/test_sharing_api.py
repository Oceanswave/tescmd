"""Tests for tescmd.api.sharing — SharingAPI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tescmd.api.sharing import SharingAPI
from tescmd.models.sharing import ShareDriverInfo, ShareInvite

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

    from tescmd.api.client import TeslaFleetClient

FLEET_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"


def _body(mock: HTTPXMock, idx: int = 0) -> dict[str, object]:
    """Parse the JSON body of the idx-th request."""
    return json.loads(mock.get_requests()[idx].content)  # type: ignore[no-any-return]


class TestAddDriver:
    @pytest.mark.asyncio
    async def test_returns_share_driver_info(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/drivers",
            json={
                "response": {
                    "share_user_id": 42,
                    "email": "test@example.com",
                    "status": "pending",
                    "public_key": "pk_abc123",
                }
            },
        )
        api = SharingAPI(mock_client)
        result = await api.add_driver(VIN, email="test@example.com")

        assert isinstance(result, ShareDriverInfo)
        assert result.share_user_id == 42
        assert result.email == "test@example.com"
        assert result.status == "pending"
        assert result.public_key == "pk_abc123"

    @pytest.mark.asyncio
    async def test_sends_email_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"share_user_id": 1, "email": "driver@test.com"}},
        )
        api = SharingAPI(mock_client)
        await api.add_driver(VIN, email="driver@test.com")

        body = _body(httpx_mock)
        assert body["email"] == "driver@test.com"
        request = httpx_mock.get_requests()[0]
        assert request.method == "POST"
        assert request.url.path == f"/api/1/vehicles/{VIN}/drivers"


class TestRemoveDriver:
    @pytest.mark.asyncio
    async def test_returns_dict(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/drivers",
            json={"response": {"result": True}},
        )
        api = SharingAPI(mock_client)
        result = await api.remove_driver(VIN, share_user_id=123)

        assert isinstance(result, dict)
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_sends_share_user_id(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {"result": True}})
        api = SharingAPI(mock_client)
        await api.remove_driver(VIN, share_user_id=123)

        body = _body(httpx_mock)
        assert body["share_user_id"] == 123
        request = httpx_mock.get_requests()[0]
        assert request.method == "DELETE"


class TestCreateInvite:
    @pytest.mark.asyncio
    async def test_returns_share_invite(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/invitations",
            json={
                "response": {
                    "id": "inv_001",
                    "code": "SHARE-XYZ",
                    "created_at": "2024-03-15T10:00:00Z",
                    "expires_at": "2024-03-22T10:00:00Z",
                    "status": "active",
                }
            },
        )
        api = SharingAPI(mock_client)
        result = await api.create_invite(VIN)

        assert isinstance(result, ShareInvite)
        assert result.id == "inv_001"
        assert result.code == "SHARE-XYZ"
        assert result.status == "active"
        assert result.created_at == "2024-03-15T10:00:00Z"
        assert result.expires_at == "2024-03-22T10:00:00Z"

    @pytest.mark.asyncio
    async def test_uses_post_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"id": "inv_002", "code": "CODE"}},
        )
        api = SharingAPI(mock_client)
        await api.create_invite(VIN)

        request = httpx_mock.get_requests()[0]
        assert request.method == "POST"
        assert request.url.path == f"/api/1/vehicles/{VIN}/invitations"


class TestRedeemInvite:
    @pytest.mark.asyncio
    async def test_returns_share_invite(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/invitations/redeem",
            json={
                "response": {
                    "id": "inv_003",
                    "code": "abc123",
                    "status": "redeemed",
                    "created_at": "2024-03-10T08:00:00Z",
                    "expires_at": "2024-03-17T08:00:00Z",
                }
            },
        )
        api = SharingAPI(mock_client)
        result = await api.redeem_invite(code="abc123")

        assert isinstance(result, ShareInvite)
        assert result.id == "inv_003"
        assert result.code == "abc123"
        assert result.status == "redeemed"

    @pytest.mark.asyncio
    async def test_sends_code_body(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"id": "inv_004", "code": "xyz789"}},
        )
        api = SharingAPI(mock_client)
        await api.redeem_invite(code="xyz789")

        body = _body(httpx_mock)
        assert body["code"] == "xyz789"
        request = httpx_mock.get_requests()[0]
        assert request.method == "POST"
        assert request.url.path == "/api/1/invitations/redeem"


class TestRevokeInvite:
    @pytest.mark.asyncio
    async def test_returns_dict(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/invitations/inv1/revoke",
            json={"response": {"result": True}},
        )
        api = SharingAPI(mock_client)
        result = await api.revoke_invite(VIN, invite_id="inv1")

        assert isinstance(result, dict)
        assert result["result"] is True

    @pytest.mark.asyncio
    async def test_correct_url_path(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": {"result": True}})
        api = SharingAPI(mock_client)
        await api.revoke_invite(VIN, invite_id="inv_abc")

        request = httpx_mock.get_requests()[0]
        assert request.method == "POST"
        assert request.url.path == f"/api/1/vehicles/{VIN}/invitations/inv_abc/revoke"


class TestListInvites:
    @pytest.mark.asyncio
    async def test_returns_list_of_share_invites(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/invitations",
            json={
                "response": [
                    {
                        "id": "inv_010",
                        "code": "CODE-A",
                        "status": "active",
                        "created_at": "2024-04-01T12:00:00Z",
                        "expires_at": "2024-04-08T12:00:00Z",
                    },
                    {
                        "id": "inv_011",
                        "code": "CODE-B",
                        "status": "active",
                        "created_at": "2024-04-02T12:00:00Z",
                        "expires_at": "2024-04-09T12:00:00Z",
                    },
                ]
            },
        )
        api = SharingAPI(mock_client)
        result = await api.list_invites(VIN)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(inv, ShareInvite) for inv in result)
        assert result[0].id == "inv_010"
        assert result[0].code == "CODE-A"
        assert result[1].id == "inv_011"
        assert result[1].code == "CODE-B"

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET_BASE}/api/1/vehicles/{VIN}/invitations",
            json={"response": []},
        )
        api = SharingAPI(mock_client)
        result = await api.list_invites(VIN)

        assert result == []

    @pytest.mark.asyncio
    async def test_uses_get_method(
        self, httpx_mock: HTTPXMock, mock_client: TeslaFleetClient
    ) -> None:
        httpx_mock.add_response(json={"response": []})
        api = SharingAPI(mock_client)
        await api.list_invites(VIN)

        request = httpx_mock.get_requests()[0]
        assert request.method == "GET"
        assert request.url.path == f"/api/1/vehicles/{VIN}/invitations"
