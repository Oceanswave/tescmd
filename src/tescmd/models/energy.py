"""Pydantic models for Tesla energy products (Powerwall, Solar)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

_EXTRA_ALLOW = ConfigDict(extra="allow")


class EnergySite(BaseModel):
    model_config = _EXTRA_ALLOW

    energy_site_id: int
    resource_type: str | None = None
    site_name: str | None = None
    gateway_id: str | None = None


class LiveStatus(BaseModel):
    model_config = _EXTRA_ALLOW

    solar_power: float | None = None
    battery_power: float | None = None
    grid_power: float | None = None
    load_power: float | None = None
    grid_status: str | None = None
    battery_level: float | None = None
    percentage_charged: float | None = None


class SiteInfo(BaseModel):
    model_config = _EXTRA_ALLOW

    energy_site_id: int | None = None
    site_name: str | None = None
    resource_type: str | None = None
    backup_reserve_percent: float | None = None
    default_real_mode: str | None = None
    storm_mode_enabled: bool | None = None
    installation_date: str | None = None


class CalendarHistory(BaseModel):
    model_config = _EXTRA_ALLOW

    serial_number: str | None = None
    time_series: list[dict[str, Any]] = []


class GridImportExportConfig(BaseModel):
    model_config = _EXTRA_ALLOW

    disallow_charge_from_grid_with_solar_installed: bool | None = None
    customer_preferred_export_rule: str | None = None
