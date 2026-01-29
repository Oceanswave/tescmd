"""Smart VIN resolution."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def resolve_vin(args: argparse.Namespace) -> str | None:
    """Resolve VIN from multiple sources in priority order.

    Resolution: positional arg > --vin flag > TESLA_VIN env > profile default > None.
    """
    vin: str | None = getattr(args, "vin_positional", None)
    if not vin:
        vin = getattr(args, "vin", None)
    if not vin:
        vin = os.environ.get("TESLA_VIN")
    return vin
