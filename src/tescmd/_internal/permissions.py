"""Cross-platform file-permission helpers."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def secure_file(path: Path) -> None:
    """Set *path* to owner-only read/write (best-effort).

    * **Unix** — ``chmod 0600``
    * **Windows** — ``icacls`` grant to current user, remove inherited ACLs

    Failures are silently ignored so callers never crash on permission
    quirks (Docker volumes, network mounts, etc.).
    """
    try:
        if sys.platform == "win32":
            _secure_file_windows(path)
        else:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _secure_file_windows(path: Path) -> None:
    """Restrict *path* to the current user via ``icacls``."""
    username = os.environ.get("USERNAME", "")
    if not username:
        return
    # Remove inherited permissions, then grant owner full control
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:(R,W)"],
        capture_output=True,
        check=False,
    )
