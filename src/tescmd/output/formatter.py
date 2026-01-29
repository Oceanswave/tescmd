from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from rich.console import Console

from tescmd.output.json_output import format_json_error, format_json_response
from tescmd.output.rich_output import RichOutput

if TYPE_CHECKING:
    from io import TextIOBase


class OutputFormatter:
    """Unified output formatter that auto-detects JSON vs Rich output.

    Selection logic:

    * If *force_format* is provided, use it unconditionally.
    * Otherwise, if *stream* (default ``sys.stdout``) is a TTY, use ``"rich"``.
    * If the stream is **not** a TTY (piped / redirected), use ``"json"``.

    When the format is ``"quiet"``, a :class:`rich.console.Console` writing to
    *stderr* is used so that normal stdout stays empty.
    """

    def __init__(
        self,
        *,
        stream: TextIOBase | Any | None = None,
        force_format: str | None = None,
    ) -> None:
        self._stream = stream or sys.stdout
        if force_format is not None:
            self._format = force_format
        elif hasattr(self._stream, "isatty") and self._stream.isatty():
            self._format = "rich"
        else:
            self._format = "json"

        # Build the Rich console — quiet mode writes to stderr.
        if self._format == "quiet":
            self._console = Console(stderr=True)
        else:
            self._console = Console()

        self._rich = RichOutput(self._console)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def format(self) -> str:  # noqa: A003
        """Return the active output format (``"rich"``, ``"json"``, or ``"quiet"``)."""
        return self._format

    @property
    def rich(self) -> RichOutput:
        """Return the underlying :class:`RichOutput` instance."""
        return self._rich

    def output(self, data: Any, *, command: str) -> None:
        """Emit *data* using the current format.

        * **json** — prints :func:`format_json_response` to stdout.
        * **rich** / **quiet** — delegates to :attr:`rich` methods when the
          data type is recognised, otherwise falls back to
          :meth:`RichOutput.info` with a ``str()`` representation.
        """
        if self._format == "json":
            print(format_json_response(data=data, command=command))  # noqa: T201
        else:
            # Rich / quiet fallback — callers normally use self.rich directly
            # for typed output; this is a catch-all.
            self._rich.info(str(data))

    def output_error(self, *, code: str, message: str, command: str) -> None:
        """Emit an error using the current format.

        * **json** — prints :func:`format_json_error` to stdout.
        * **rich** / **quiet** — prints via :meth:`RichOutput.error`.
        """
        if self._format == "json":
            print(format_json_error(code=code, message=message, command=command))  # noqa: T201
        else:
            self._rich.error(message)
