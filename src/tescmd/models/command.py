from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CommandResult(BaseModel):
    """The inner result payload of a vehicle command."""

    result: bool
    reason: str = ""


class CommandResponse(BaseModel):
    """Envelope returned by the Fleet API for command endpoints."""

    model_config = ConfigDict(extra="allow")

    response: CommandResult
