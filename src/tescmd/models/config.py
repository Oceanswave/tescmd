from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Profile(BaseModel):
    """A named profile grouping common CLI settings."""

    region: str = "na"
    vin: str | None = None
    output_format: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


class AppSettings(BaseSettings):
    """Application-wide settings populated from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TESLA_",
        extra="ignore",
    )

    client_id: str | None = None
    client_secret: str | None = None
    domain: str | None = None
    vin: str | None = None
    region: str = "na"
    token_file: str | None = None
    config_dir: str = "~/.config/tescmd"
    output_format: str | None = None
    profile: str = "default"
    access_token: str | None = None
    refresh_token: str | None = None
