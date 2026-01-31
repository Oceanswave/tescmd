"""OAuth2 PKCE helpers, partner registration, and interactive login flow."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
import webbrowser
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx

from tescmd.api.client import REGION_BASE_URLS
from tescmd.api.errors import AuthError
from tescmd.auth.server import OAuthCallbackServer
from tescmd.models.auth import (
    AUTHORIZE_URL,
    PARTNER_SCOPES,
    TOKEN_URL,
    TokenData,
    decode_jwt_scopes,
)

if TYPE_CHECKING:
    from tescmd.auth.token_store import TokenStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------


def _generate_code_verifier() -> str:
    """Return a 128-character base64url code verifier (no padding)."""
    return secrets.token_urlsafe(96)[:128]


def _generate_code_challenge(verifier: str) -> str:
    """Compute S256 code challenge for the given *verifier*."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_auth_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    code_challenge: str,
    state: str,
    *,
    force_consent: bool = False,
) -> str:
    """Build the full Tesla authorization URL.

    When *force_consent* is ``True`` the ``prompt_missing_scopes=true``
    parameter is added so Tesla prompts the user to approve any scopes
    that were not granted in a previous consent.  This is Tesla's
    proprietary parameter (not the standard ``prompt=consent``).
    """
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if force_consent:
        params["prompt_missing_scopes"] = "true"
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------


async def exchange_code(
    code: str,
    code_verifier: str,
    client_id: str,
    client_secret: str | None = None,
    redirect_uri: str = "http://localhost:8085/callback",
) -> TokenData:
    """Exchange an authorization code for tokens."""
    payload: dict[str, Any] = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    if client_secret is not None:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=payload)
    if resp.status_code != 200:
        raise AuthError(f"Token exchange failed: {resp.text}", status_code=resp.status_code)
    return TokenData.model_validate(resp.json())


async def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str | None = None,
) -> TokenData:
    """Use a refresh token to obtain new tokens."""
    payload: dict[str, Any] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if client_secret is not None:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=payload)
    if resp.status_code != 200:
        raise AuthError(f"Token refresh failed: {resp.text}", status_code=resp.status_code)
    return TokenData.model_validate(resp.json())


# ---------------------------------------------------------------------------
# Partner registration (one-time per region)
# ---------------------------------------------------------------------------


async def get_partner_token(
    client_id: str,
    client_secret: str,
    region: str = "na",
) -> tuple[str, list[str]]:
    """Obtain a partner token via *client_credentials* grant.

    The ``audience`` parameter tells Tesla which regional endpoint the
    token is for.

    Returns a ``(token, granted_scopes)`` tuple.  *granted_scopes* are
    decoded from the JWT ``scp`` claim so callers can verify that the
    partner registration will cover all requested scopes.
    """
    audience = REGION_BASE_URLS.get(region)
    if audience is None:
        msg = f"Unknown region {region!r}; expected one of {sorted(REGION_BASE_URLS)}"
        raise AuthError(msg)

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": " ".join(PARTNER_SCOPES),
        "audience": audience,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data=payload)
    if resp.status_code != 200:
        raise AuthError(
            f"Partner token request failed: {resp.text}",
            status_code=resp.status_code,
        )
    data: dict[str, Any] = resp.json()
    token: str = data["access_token"]

    granted = decode_jwt_scopes(token) or []
    logger.debug("Partner token scopes: requested=%s, granted=%s", PARTNER_SCOPES, granted)

    return token, granted


async def register_partner_account(
    client_id: str,
    client_secret: str,
    domain: str = "localhost",
    region: str = "na",
) -> tuple[dict[str, Any], list[str]]:
    """Register the application with the Tesla Fleet API for *region*.

    This must be called once per region before the Fleet API will accept
    requests.  It is safe to call more than once (idempotent).

    Returns a ``(response_body, partner_scopes)`` tuple.
    *partner_scopes* are the scopes actually granted in the partner
    token, which determines the ceiling for user token scopes.
    """
    base_url = REGION_BASE_URLS.get(region)
    if base_url is None:
        msg = f"Unknown region {region!r}; expected one of {sorted(REGION_BASE_URLS)}"
        raise AuthError(msg)

    partner_token, granted_scopes = await get_partner_token(client_id, client_secret, region)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{base_url}/api/1/partner_accounts",
            json={"domain": domain},
            headers={"Authorization": f"Bearer {partner_token}"},
        )

    if resp.status_code >= 400:
        raise AuthError(
            f"Partner registration failed (HTTP {resp.status_code}): {resp.text}",
            status_code=resp.status_code,
        )
    result: dict[str, Any] = resp.json()
    return result, granted_scopes


# ---------------------------------------------------------------------------
# Scope extraction
# ---------------------------------------------------------------------------


def _extract_granted_scopes(token: TokenData, *, requested: list[str]) -> list[str]:
    """Return the scopes actually granted in the token response.

    Checks three sources in priority order:
    1. ``token.scope`` — the ``scope`` field from the OAuth token response
    2. JWT ``scp`` claim — decoded from the access token payload
    3. *requested* — falls back to whatever we asked for
    """
    if token.scope:
        return token.scope.split()

    jwt_scopes = decode_jwt_scopes(token.access_token)
    if jwt_scopes is not None:
        return jwt_scopes

    return requested


# ---------------------------------------------------------------------------
# Full interactive login flow
# ---------------------------------------------------------------------------


async def login_flow(
    client_id: str,
    client_secret: str | None,
    redirect_uri: str,
    scopes: list[str],
    port: int,
    token_store: TokenStore,
    region: str = "na",
    *,
    force_consent: bool = False,
) -> TokenData:
    """Run the full OAuth2 PKCE login flow interactively.

    1. Generate PKCE pair
    2. Start local callback server
    3. Open browser to authorization URL
    4. Wait for redirect with auth code
    5. Exchange code for tokens
    6. Persist to *token_store*

    When *force_consent* is ``True`` the authorization URL includes
    ``prompt_missing_scopes=true`` so Tesla prompts for any new scopes.
    """
    verifier = _generate_code_verifier()
    challenge = _generate_code_challenge(verifier)
    state = secrets.token_urlsafe(32)

    server = OAuthCallbackServer(port=port)
    server.start()
    try:
        url = build_auth_url(
            client_id,
            redirect_uri,
            scopes,
            challenge,
            state,
            force_consent=force_consent,
        )
        webbrowser.open(url)

        code, callback_state = server.wait_for_callback(timeout=120)
    finally:
        server.stop()

    if code is None:
        raise AuthError("OAuth callback timed out or was cancelled")

    if callback_state != state:
        raise AuthError("OAuth state mismatch — possible CSRF attack")

    token = await exchange_code(
        code=code,
        code_verifier=verifier,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )

    # Determine actually granted scopes — prefer the token response's scope
    # field, then JWT payload, then fall back to what we requested.
    granted = _extract_granted_scopes(token, requested=scopes)

    token_store.save(
        access_token=token.access_token,
        refresh_token=token.refresh_token or "",
        expires_at=time.time() + token.expires_in,
        scopes=granted,
        region=region,
    )
    return token
