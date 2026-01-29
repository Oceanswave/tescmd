from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SCOPES: list[str] = [
    "openid",
    "offline_access",
    "vehicle_device_data",
    "vehicle_cmds",
    "vehicle_charging_cmds",
]

DEFAULT_REDIRECT_URI: str = "https://localhost/callback"

AUTH_BASE_URL: str = "https://auth.tesla.com"
AUTHORIZE_URL: str = f"{AUTH_BASE_URL}/oauth2/v3/authorize"
TOKEN_URL: str = f"{AUTH_BASE_URL}/oauth2/v3/token"

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TokenData(BaseModel):
    """Raw token response from the Tesla OAuth endpoint."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str | None = None
    id_token: str | None = None


class TokenMeta(BaseModel):
    """Metadata stored alongside the persisted token."""

    expires_at: float
    scopes: list[str]
    region: str


class AuthConfig(BaseModel):
    """Configuration needed to start an OAuth flow."""

    client_id: str
    client_secret: str | None = None
    redirect_uri: str = DEFAULT_REDIRECT_URI
    scopes: list[str] = DEFAULT_SCOPES
