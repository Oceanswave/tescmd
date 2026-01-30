"""Execution tests for the sharing CLI commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from click.testing import CliRunner

from tescmd.cli.main import cli

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

FLEET = "https://fleet-api.prd.na.vn.cloud.tesla.com"
VIN = "5YJ3E1EA1NF000001"


def _request_body(httpx_mock: HTTPXMock, idx: int = 0) -> dict[str, object]:
    """Parse the JSON body of the *idx*-th captured request."""
    return json.loads(httpx_mock.get_requests()[idx].content)  # type: ignore[no-any-return]


def _request_url(httpx_mock: HTTPXMock, idx: int = 0) -> str:
    """Return the full URL string of the *idx*-th captured request."""
    return str(httpx_mock.get_requests()[idx].url)


# ---------------------------------------------------------------------------
# sharing add-driver
# ---------------------------------------------------------------------------


class TestSharingAddDriver:
    def test_add_driver_returns_share_driver_info(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/drivers",
            json={
                "response": {
                    "share_user_id": 42,
                    "email": "test@example.com",
                    "status": "pending",
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "sharing", "add-driver", VIN, "test@example.com"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "sharing.add-driver"
        assert parsed["data"]["share_user_id"] == 42
        assert parsed["data"]["email"] == "test@example.com"
        assert parsed["data"]["status"] == "pending"

    def test_add_driver_sends_email_in_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/drivers",
            json={
                "response": {
                    "share_user_id": 42,
                    "email": "driver@tesla.com",
                    "status": "pending",
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "add-driver", VIN, "driver@tesla.com"],
            catch_exceptions=False,
        )

        body = _request_body(httpx_mock)
        assert body["email"] == "driver@tesla.com"

    def test_add_driver_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "share_user_id": 1,
                    "email": "a@b.com",
                    "status": "pending",
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "add-driver", VIN, "a@b.com"],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert f"/api/1/vehicles/{VIN}/drivers" in _request_url(httpx_mock)


# ---------------------------------------------------------------------------
# sharing remove-driver
# ---------------------------------------------------------------------------


class TestSharingRemoveDriver:
    def test_remove_driver_returns_result(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/drivers/remove",
            json={"response": {"result": True}},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "sharing", "remove-driver", VIN, "42"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "sharing.remove-driver"
        assert parsed["data"]["result"] is True

    def test_remove_driver_sends_share_user_id_in_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/drivers/remove",
            json={"response": {"result": True}},
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "remove-driver", VIN, "99"],
            catch_exceptions=False,
        )

        body = _request_body(httpx_mock)
        assert body["share_user_id"] == 99

    def test_remove_driver_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"result": True}},
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "remove-driver", VIN, "42"],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert f"/api/1/vehicles/{VIN}/drivers/remove" in _request_url(httpx_mock)


# ---------------------------------------------------------------------------
# sharing create-invite
# ---------------------------------------------------------------------------


class TestSharingCreateInvite:
    def test_create_invite_returns_invite(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations",
            json={
                "response": {
                    "id": "inv-123",
                    "code": "ABC123",
                    "created_at": "2024-01-01T00:00:00Z",
                    "expires_at": "2024-02-01T00:00:00Z",
                    "status": "pending",
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "sharing", "create-invite", VIN],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "sharing.create-invite"
        assert parsed["data"]["id"] == "inv-123"
        assert parsed["data"]["code"] == "ABC123"
        assert parsed["data"]["status"] == "pending"
        assert parsed["data"]["created_at"] == "2024-01-01T00:00:00Z"
        assert parsed["data"]["expires_at"] == "2024-02-01T00:00:00Z"

    def test_create_invite_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "id": "inv-456",
                    "code": "XYZ789",
                    "status": "pending",
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "create-invite", VIN],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert f"/api/1/vehicles/{VIN}/invitations" in _request_url(httpx_mock)

    def test_create_invite_sends_no_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations",
            json={
                "response": {
                    "id": "inv-789",
                    "code": "DEF456",
                    "status": "pending",
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "create-invite", VIN],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        # create_invite does not send a JSON body
        assert req.content == b"" or req.content is None


# ---------------------------------------------------------------------------
# sharing redeem-invite
# ---------------------------------------------------------------------------


class TestSharingRedeemInvite:
    def test_redeem_invite_returns_invite(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations/redeem",
            json={
                "response": {
                    "id": "inv-123",
                    "code": "ABC123",
                    "created_at": "2024-01-01T00:00:00Z",
                    "expires_at": "2024-02-01T00:00:00Z",
                    "status": "redeemed",
                }
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "sharing", "redeem-invite", VIN, "ABC123"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "sharing.redeem-invite"
        assert parsed["data"]["id"] == "inv-123"
        assert parsed["data"]["code"] == "ABC123"
        assert parsed["data"]["status"] == "redeemed"

    def test_redeem_invite_sends_code_in_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations/redeem",
            json={
                "response": {
                    "id": "inv-123",
                    "code": "MYCODE",
                    "status": "redeemed",
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "redeem-invite", VIN, "MYCODE"],
            catch_exceptions=False,
        )

        body = _request_body(httpx_mock)
        assert body["code"] == "MYCODE"

    def test_redeem_invite_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={
                "response": {
                    "id": "inv-999",
                    "code": "ZZZ",
                    "status": "redeemed",
                }
            },
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "redeem-invite", VIN, "ZZZ"],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert f"/api/1/vehicles/{VIN}/invitations/redeem" in _request_url(httpx_mock)


# ---------------------------------------------------------------------------
# sharing revoke-invite
# ---------------------------------------------------------------------------


class TestSharingRevokeInvite:
    def test_revoke_invite_returns_result(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations/inv-123/revoke",
            json={"response": {"result": True}},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "sharing", "revoke-invite", VIN, "inv-123"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "sharing.revoke-invite"
        assert parsed["data"]["result"] is True

    def test_revoke_invite_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={"response": {"result": True}},
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "revoke-invite", VIN, "inv-456"],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        assert req.method == "POST"
        assert f"/api/1/vehicles/{VIN}/invitations/inv-456/revoke" in _request_url(
            httpx_mock
        )

    def test_revoke_invite_sends_no_body(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations/inv-789/revoke",
            json={"response": {"result": True}},
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "revoke-invite", VIN, "inv-789"],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        # revoke_invite does not send a JSON body
        assert req.content == b"" or req.content is None


# ---------------------------------------------------------------------------
# sharing list-invites
# ---------------------------------------------------------------------------


class TestSharingListInvites:
    def test_list_invites_returns_invites(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations",
            json={
                "response": [
                    {
                        "id": "inv-123",
                        "code": "ABC123",
                        "created_at": "2024-01-01T00:00:00Z",
                        "expires_at": "2024-02-01T00:00:00Z",
                        "status": "pending",
                    },
                    {
                        "id": "inv-456",
                        "code": "DEF456",
                        "created_at": "2024-03-01T00:00:00Z",
                        "expires_at": "2024-04-01T00:00:00Z",
                        "status": "redeemed",
                    },
                ]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "sharing", "list-invites", VIN],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "sharing.list-invites"
        assert isinstance(parsed["data"], list)
        assert len(parsed["data"]) == 2
        assert parsed["data"][0]["id"] == "inv-123"
        assert parsed["data"][0]["code"] == "ABC123"
        assert parsed["data"][0]["status"] == "pending"
        assert parsed["data"][1]["id"] == "inv-456"
        assert parsed["data"][1]["status"] == "redeemed"

    def test_list_invites_empty(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            url=f"{FLEET}/api/1/vehicles/{VIN}/invitations",
            json={"response": []},
        )
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--format", "json", "sharing", "list-invites", VIN],
            catch_exceptions=False,
        )

        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["ok"] is True
        assert parsed["command"] == "sharing.list-invites"
        assert parsed["data"] == []

    def test_list_invites_hits_correct_endpoint(
        self, cli_env: dict[str, str], httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_response(
            json={"response": []},
        )
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--format", "json", "sharing", "list-invites", VIN],
            catch_exceptions=False,
        )

        req = httpx_mock.get_requests()[0]
        assert req.method == "GET"
        assert f"/api/1/vehicles/{VIN}/invitations" in _request_url(httpx_mock)
