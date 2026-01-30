"""Smart VIN resolution and validation."""

from __future__ import annotations

import os
import re

# ISO 3779: VINs are 17 alphanumeric characters, excluding I, O, Q.
_VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


class InvalidVINError(ValueError):
    """Raised when a VIN fails format validation."""


def validate_vin(vin: str) -> str:
    """Validate that *vin* matches the ISO 3779 VIN format.

    Returns the uppercased VIN on success; raises :class:`InvalidVINError`
    on failure.
    """
    upper = vin.upper()
    if not _VIN_PATTERN.match(upper):
        raise InvalidVINError(
            f"Invalid VIN {vin!r}: must be 17 alphanumeric characters "
            "(excluding I, O, Q per ISO 3779)."
        )
    return upper


def resolve_vin(
    *,
    vin_positional: str | None = None,
    vin_flag: str | None = None,
) -> str | None:
    """Resolve VIN from multiple sources in priority order.

    Resolution: positional arg > --vin flag > TESLA_VIN env > None.
    """
    if vin_positional:
        return vin_positional
    if vin_flag:
        return vin_flag
    return os.environ.get("TESLA_VIN")
