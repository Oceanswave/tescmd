from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel


def _serialize(obj: Any) -> Any:
    """Convert *obj* to a JSON-friendly structure.

    * :class:`pydantic.BaseModel` instances are dumped via
      :meth:`~pydantic.BaseModel.model_dump` with *exclude_none=True*.
    * Lists are recursed element-wise.
    * Everything else is returned as-is (``json.dumps`` handles the rest via
      *default=str*).
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(exclude_none=True)
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return obj


def format_json_response(*, data: Any, command: str) -> str:
    """Return a JSON envelope for a successful response.

    The envelope has the shape::

        {
          "ok": true,
          "command": "<command>",
          "data": <serialised payload>,
          "timestamp": "<ISO-8601 UTC>"
        }
    """
    envelope: dict[str, Any] = {
        "ok": True,
        "command": command,
        "data": _serialize(data),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return json.dumps(envelope, indent=2, default=str)


def format_json_error(
    *,
    code: str,
    message: str,
    command: str,
    **extra: Any,
) -> str:
    """Return a JSON envelope for an error response.

    The envelope has the shape::

        {
          "ok": false,
          "command": "<command>",
          "error": {"code": "...", "message": "...", ...extra},
          "timestamp": "<ISO-8601 UTC>"
        }
    """
    error_body: dict[str, Any] = {"code": code, "message": message, **extra}
    envelope: dict[str, Any] = {
        "ok": False,
        "command": command,
        "error": error_body,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return json.dumps(envelope, indent=2, default=str)
