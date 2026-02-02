"""Extended OAuth tests — token exchange, refresh, partner tokens, and registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tescmd.api.errors import AuthError
from tescmd.auth.oauth import (
    exchange_code,
    get_partner_token,
    refresh_access_token,
    register_partner_account,
)

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock

TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_exchange_code_success(self, httpx_mock: HTTPXMock) -> None:
        """Successful code exchange returns TokenData with expected fields."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={
                "access_token": "at-123",
                "token_type": "Bearer",
                "expires_in": 3600,
                "refresh_token": "rt-456",
            },
        )
        result = await exchange_code(
            code="auth-code",
            code_verifier="verifier",
            client_id="client-id",
        )
        assert result.access_token == "at-123"
        assert result.refresh_token == "rt-456"
        assert result.expires_in == 3600

    @pytest.mark.asyncio
    async def test_exchange_code_failure_raises_auth_error(self, httpx_mock: HTTPXMock) -> None:
        """Non-200 response from token endpoint raises AuthError."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            status_code=400,
            text="invalid_grant",
        )
        with pytest.raises(AuthError, match="Token exchange failed"):
            await exchange_code(
                code="bad-code",
                code_verifier="verifier",
                client_id="client-id",
            )


class TestRefreshAccessToken:
    @pytest.mark.asyncio
    async def test_refresh_success(self, httpx_mock: HTTPXMock) -> None:
        """Successful token refresh returns TokenData with new tokens."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={
                "access_token": "new-at",
                "token_type": "Bearer",
                "expires_in": 7200,
                "refresh_token": "new-rt",
            },
        )
        result = await refresh_access_token(
            refresh_token="old-rt",
            client_id="client-id",
        )
        assert result.access_token == "new-at"
        assert result.expires_in == 7200

    @pytest.mark.asyncio
    async def test_refresh_failure_raises_auth_error(self, httpx_mock: HTTPXMock) -> None:
        """Non-200 response during refresh raises AuthError."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            status_code=401,
            text="invalid_token",
        )
        with pytest.raises(AuthError, match="Token refresh failed"):
            await refresh_access_token(
                refresh_token="bad-rt",
                client_id="client-id",
            )


class TestGetPartnerToken:
    @pytest.mark.asyncio
    async def test_partner_token_success(self, httpx_mock: HTTPXMock) -> None:
        """Successful partner token request returns access token string."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={
                "access_token": "partner-token-123",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
        token, granted_scopes = await get_partner_token(
            client_id="cid",
            client_secret="csecret",
            region="na",
        )
        assert token == "partner-token-123"
        # Non-JWT token → no scopes decoded
        assert granted_scopes == []

    @pytest.mark.asyncio
    async def test_partner_token_invalid_region(self) -> None:
        """Invalid region raises AuthError before any HTTP call."""
        with pytest.raises(AuthError, match="Unknown region"):
            await get_partner_token(
                client_id="cid",
                client_secret="csecret",
                region="invalid",
            )


NA_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
PARTNER_URL = f"{NA_BASE}/api/1/partner_accounts"


class TestRegisterPartnerAccount:
    """Tests for register_partner_account() — including idempotent 422 handling."""

    @pytest.mark.asyncio
    async def test_success_returns_response_and_scopes(self, httpx_mock: HTTPXMock) -> None:
        """Normal 200 returns the JSON body and partner scopes."""
        # Mock partner token request
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={"access_token": "pt-123", "token_type": "Bearer", "expires_in": 3600},
        )
        # Mock registration endpoint
        httpx_mock.add_response(
            url=PARTNER_URL,
            method="POST",
            json={"response": {"domain": "example.com"}},
        )
        result, _scopes = await register_partner_account(
            client_id="cid",
            client_secret="csecret",
            domain="example.com",
            region="na",
        )
        assert result == {"response": {"domain": "example.com"}}
        assert "already_registered" not in result

    @pytest.mark.asyncio
    async def test_422_already_taken_returns_success(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 422 'already been taken' is treated as success (idempotent)."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={"access_token": "pt-123", "token_type": "Bearer", "expires_in": 3600},
        )
        httpx_mock.add_response(
            url=PARTNER_URL,
            method="POST",
            status_code=422,
            json={
                "response": None,
                "error": "Validation failed: Public key hash has already been taken",
                "error_description": "",
            },
        )
        result, _scopes = await register_partner_account(
            client_id="cid",
            client_secret="csecret",
            domain="example.com",
            region="na",
        )
        assert result["already_registered"] is True

    @pytest.mark.asyncio
    async def test_422_other_error_raises(self, httpx_mock: HTTPXMock) -> None:
        """HTTP 422 without 'already been taken' still raises AuthError."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={"access_token": "pt-123", "token_type": "Bearer", "expires_in": 3600},
        )
        httpx_mock.add_response(
            url=PARTNER_URL,
            method="POST",
            status_code=422,
            json={"error": "Validation failed: Something else went wrong"},
        )
        with pytest.raises(AuthError, match="Partner registration failed"):
            await register_partner_account(
                client_id="cid",
                client_secret="csecret",
                domain="example.com",
                region="na",
            )

    @pytest.mark.asyncio
    async def test_non_422_error_raises(self, httpx_mock: HTTPXMock) -> None:
        """Other HTTP errors (e.g. 412, 500) still raise AuthError."""
        httpx_mock.add_response(
            url=TOKEN_URL,
            method="POST",
            json={"access_token": "pt-123", "token_type": "Bearer", "expires_in": 3600},
        )
        httpx_mock.add_response(
            url=PARTNER_URL,
            method="POST",
            status_code=412,
            text="Origin mismatch",
        )
        with pytest.raises(AuthError, match="Partner registration failed"):
            await register_partner_account(
                client_id="cid",
                client_secret="csecret",
                domain="example.com",
                region="na",
            )

    @pytest.mark.asyncio
    async def test_invalid_region_raises(self) -> None:
        """Invalid region raises AuthError before any HTTP call."""
        with pytest.raises(AuthError, match="Unknown region"):
            await register_partner_account(
                client_id="cid",
                client_secret="csecret",
                domain="example.com",
                region="invalid",
            )
