from __future__ import annotations

from pydantic import BaseModel, field_validator
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

    @field_validator("domain", mode="before")
    @classmethod
    def _lowercase_domain(cls, v: str | None) -> str | None:
        """Tesla Fleet API rejects domains with uppercase characters."""
        if v is not None:
            return v.lower()
        return v

    region: str = "na"
    token_file: str | None = None
    config_dir: str = "~/.config/tescmd"
    output_format: str | None = None
    profile: str = "default"
    setup_tier: str | None = None
    github_repo: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None

    # Cache settings (TESLA_CACHE_ENABLED, TESLA_CACHE_TTL, TESLA_CACHE_DIR)
    cache_enabled: bool = True
    cache_ttl: int = 60
    cache_dir: str = "~/.cache/tescmd"

    # Command protocol: auto | signed | unsigned
    # auto = use signed when keys available, fall back to unsigned
    # signed = require signed (error if no keys)
    # unsigned = force legacy REST path
    command_protocol: str = "auto"
