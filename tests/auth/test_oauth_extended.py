"""Extended OAuth tests — token exchange, refresh, and partner tokens."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tescmd.api.errors import AuthError
from tescmd.auth.oauth import exchange_code, get_partner_token, refresh_access_token

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
        token = await get_partner_token(
            client_id="cid",
            client_secret="csecret",
            region="na",
        )
        assert token == "partner-token-123"

    @pytest.mark.asyncio
    async def test_partner_token_invalid_region(self) -> None:
        """Invalid region raises AuthError before any HTTP call."""
        with pytest.raises(AuthError, match="Unknown region"):
            await get_partner_token(
                client_id="cid",
                client_secret="csecret",
                region="invalid",
            )
