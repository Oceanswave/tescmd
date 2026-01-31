"""Exception hierarchy for Tesla Fleet API errors."""

from __future__ import annotations


class TeslaAPIError(Exception):
    """Base exception for all Tesla Fleet API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthError(TeslaAPIError):
    """Raised on 401 / authentication failures."""


class VehicleAsleepError(TeslaAPIError):
    """Raised when the vehicle is asleep (HTTP 408)."""


class VehicleNotFoundError(TeslaAPIError):
    """Raised when the requested vehicle does not exist."""


class CommandFailedError(TeslaAPIError):
    """Raised when a vehicle command is rejected by the API."""

    def __init__(
        self,
        message: str,
        reason: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message, status_code)
        self.reason = reason


class RateLimitError(TeslaAPIError):
    """Raised on HTTP 429 — too many requests."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class RegistrationRequiredError(TeslaAPIError):
    """Raised on HTTP 412 — app not registered with regional Fleet API."""


class NetworkError(TeslaAPIError):
    """Raised on connection / timeout errors."""


class ConfigError(Exception):
    """Raised for configuration problems (not an API error)."""


class TierError(ConfigError):
    """Command requires full-tier setup but only readonly is configured."""


class SessionError(TeslaAPIError):
    """ECDH session handshake failed."""


class MissingScopesError(AuthError):
    """Raised on HTTP 403 when the token lacks required OAuth scopes."""


class KeyNotEnrolledError(TeslaAPIError):
    """Vehicle rejected the command — key not enrolled."""
