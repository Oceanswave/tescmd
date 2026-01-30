"""Pydantic models for Tesla vehicle sharing (drivers and invites)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_EXTRA_ALLOW = ConfigDict(extra="allow")


class ShareDriverInfo(BaseModel):
    model_config = _EXTRA_ALLOW

    share_user_id: int | None = None
    email: str | None = None
    status: str | None = None
    public_key: str | None = None


class ShareInvite(BaseModel):
    model_config = _EXTRA_ALLOW

    id: str | None = None
    code: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    status: str | None = None
