"""Pydantic models for Tesla user account data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_EXTRA_ALLOW = ConfigDict(extra="allow")


class UserInfo(BaseModel):
    model_config = _EXTRA_ALLOW

    email: str | None = None
    full_name: str | None = None
    profile_image_url: str | None = None


class UserRegion(BaseModel):
    model_config = _EXTRA_ALLOW

    region: str | None = None
    fleet_api_base_url: str | None = None


class VehicleOrder(BaseModel):
    model_config = _EXTRA_ALLOW

    order_id: str | None = None
    vin: str | None = None
    model: str | None = None
    status: str | None = None


class FeatureConfig(BaseModel):
    model_config = _EXTRA_ALLOW

    signaling: dict[str, bool] | None = None
