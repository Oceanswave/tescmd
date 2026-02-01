from __future__ import annotations

import base64
import json
import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope constants
# ---------------------------------------------------------------------------

VEHICLE_SCOPES: list[str] = [
    "vehicle_device_data",
    "vehicle_cmds",
    "vehicle_charging_cmds",
    "vehicle_location",
]

ENERGY_SCOPES: list[str] = [
    "energy_device_data",
    "energy_cmds",
]

USER_SCOPES: list[str] = [
    "user_data",
]

PARTNER_SCOPES: list[str] = [
    "openid",
    *VEHICLE_SCOPES,
    *ENERGY_SCOPES,
    *USER_SCOPES,
]

DEFAULT_SCOPES: list[str] = [
    "openid",
    "offline_access",
    *VEHICLE_SCOPES,
    *ENERGY_SCOPES,
    *USER_SCOPES,
]

DEFAULT_PORT: int = 8085
DEFAULT_REDIRECT_URI: str = f"http://localhost:{DEFAULT_PORT}/callback"

AUTH_BASE_URL: str = "https://auth.tesla.com"
AUTHORIZE_URL: str = f"{AUTH_BASE_URL}/oauth2/v3/authorize"
TOKEN_URL: str = f"{AUTH_BASE_URL}/oauth2/v3/token"

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TokenData(BaseModel, extra="allow"):
    """Raw token response from the Tesla OAuth endpoint."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None  # space-separated granted scopes (if returned by server)


class TokenMeta(BaseModel):
    """Metadata stored alongside the persisted token."""

    expires_at: float
    scopes: list[str]
    region: str


def decode_jwt_scopes(token: str) -> list[str] | None:
    """Extract scopes from a JWT access token without verifying the signature.

    Tesla access tokens are JWTs with an ``scp`` claim containing the
    granted scopes.  Returns ``None`` if the token isn't a JWT or the
    ``scp`` claim is absent.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        # JWT uses base64url encoding; add padding for stdlib decoder
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload: dict[str, Any] = json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError):
        logger.debug("Failed to decode JWT payload")
        return None

    scp = payload.get("scp")
    if isinstance(scp, list):
        return [str(s) for s in scp]
    return None


def decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode the full JWT payload without verifying the signature.

    Returns the payload dict, or ``None`` if the token isn't a valid JWT.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload: dict[str, Any] = json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError):
        logger.debug("Failed to decode JWT payload")
        return None
    return payload


class AuthConfig(BaseModel):
    """Configuration needed to start an OAuth flow."""

    client_id: str
    client_secret: str | None = None
    redirect_uri: str = DEFAULT_REDIRECT_URI
    scopes: list[str] = DEFAULT_SCOPES
