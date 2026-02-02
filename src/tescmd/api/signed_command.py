"""Signed command API — Vehicle Command Protocol over the signed_command endpoint.

Routes commands through either the signed ECDH/HMAC path or the unsigned
REST path depending on the command's registry entry.

This class matches the :class:`CommandAPI` interface so callers (CLI modules)
don't need to know which protocol path is in use.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from tescmd.api.errors import KeyNotEnrolledError, SessionError, TeslaAPIError
from tescmd.models.command import CommandResponse, CommandResult
from tescmd.protocol.commands import get_command_spec
from tescmd.protocol.encoder import (
    build_signed_command,
    default_expiry,
    encode_routable_message,
)
from tescmd.protocol.metadata import encode_metadata
from tescmd.protocol.payloads import build_command_payload
from tescmd.protocol.protobuf.messages import (
    FAULT_DESCRIPTIONS,
    KEY_FAULTS,
    MessageFault,
    RoutableMessage,
)
from tescmd.protocol.signer import compute_hmac_tag

if TYPE_CHECKING:
    from tescmd.api.client import TeslaFleetClient
    from tescmd.api.command import CommandAPI
    from tescmd.protocol.protobuf.messages import Domain
    from tescmd.protocol.session import SessionManager

logger = logging.getLogger(__name__)

# Faults indicating the ECDH session is stale and a fresh handshake is needed.
_STALE_SESSION_FAULTS: frozenset[MessageFault] = frozenset(
    {
        MessageFault.ERROR_INVALID_SIGNATURE,
        MessageFault.ERROR_INVALID_TOKEN_OR_COUNTER,
        MessageFault.ERROR_INCORRECT_EPOCH,
        MessageFault.ERROR_TIME_EXPIRED,
    }
)


class SignedCommandAPI:
    """Vehicle command API using the Vehicle Command Protocol (signed channel).

    Commands registered in the protocol command registry with
    ``requires_signing=True`` are routed through the ECDH session + HMAC
    path.  Unsigned commands (e.g. ``wake_up``) pass through to the
    legacy REST endpoint via the wrapped :class:`CommandAPI`.

    Named methods (``charge_start``, ``door_lock``, etc.) are created
    dynamically via :meth:`__getattr__` — each returns a dispatch wrapper
    that routes through :meth:`_command`, which picks the signed or
    unsigned path based on the command registry.
    """

    def __init__(
        self,
        client: TeslaFleetClient,
        session_mgr: SessionManager,
        unsigned_api: CommandAPI,
    ) -> None:
        self._client = client
        self._session_mgr = session_mgr
        self._unsigned_api = unsigned_api

    async def _command(
        self, vin: str, command: str, body: dict[str, Any] | None = None
    ) -> CommandResponse:
        """Execute a command — signed or unsigned depending on registry."""
        spec = get_command_spec(command)

        # Unknown commands or unsigned commands → legacy REST path
        if spec is None or not spec.requires_signing:
            return await self._unsigned_api._command(vin, command, body)

        return await self._signed_command(vin, command, body, domain=spec.domain)

    async def _signed_command(
        self,
        vin: str,
        command: str,
        body: dict[str, Any] | None,
        *,
        domain: Domain,
        _retried: bool = False,
    ) -> CommandResponse:
        """Build, sign, and send a command via the signed_command endpoint."""
        session = await self._session_mgr.get_session(vin, domain)

        # Build protobuf payload for the command
        payload = build_command_payload(command, body)

        # Metadata + HMAC
        counter = session.next_counter()
        expires_at = default_expiry(time_zero=session.time_zero)
        metadata_bytes = encode_metadata(
            epoch=session.epoch,
            expires_at=expires_at,
            counter=counter,
            domain=domain,
            vin=vin,
        )
        hmac_tag = compute_hmac_tag(
            session.signing_key,
            metadata_bytes,
            payload,
        )

        logger.debug(
            "Signed command '%s' for %s: counter=%d, expires_at=%d "
            "(time_zero=%.1f), payload=%s, metadata=%s, hmac_tag=%s",
            command,
            vin,
            counter,
            expires_at,
            session.time_zero,
            payload.hex(),
            metadata_bytes.hex(),
            hmac_tag.hex(),
        )

        # Build RoutableMessage
        msg = build_signed_command(
            domain=domain,
            payload=payload,
            client_public_key=self._session_mgr.client_public_key,
            epoch=session.epoch,
            counter=counter,
            expires_at=expires_at,
            hmac_tag=hmac_tag,
        )
        encoded = encode_routable_message(msg)

        logger.debug(
            "Encoded RoutableMessage for %s: %s",
            vin,
            encoded[:80] + "..." if len(encoded) > 80 else encoded,
        )

        # POST to signed_command endpoint
        try:
            data = await self._client.post(
                f"/api/1/vehicles/{vin}/signed_command",
                json={"routable_message": encoded},
            )
        except TeslaAPIError as exc:
            # Check for key-not-enrolled error pattern
            err_msg = str(exc).lower()
            if "not enrolled" in err_msg or "unknown key" in err_msg:
                raise KeyNotEnrolledError(
                    f"Key not enrolled on vehicle {vin}. "
                    "Enroll via 'tescmd key enroll' and approve in the Tesla app.",
                    status_code=422,
                ) from exc
            # Let domain-specific errors (VehicleAsleepError, RateLimitError,
            # etc.) propagate so callers like auto_wake() can handle them.
            raise

        result, fault = self._parse_signed_response(data, vin, command, domain)
        if result is not None:
            return result

        # Stale session — _parse_signed_response already invalidated the cache.
        # Retry once with a fresh handshake.
        if _retried:
            fault_name = fault.name if fault else "unknown"
            desc = FAULT_DESCRIPTIONS.get(fault, fault_name) if fault else fault_name
            raise SessionError(
                f"Signed command '{command}' failed for {vin} after session refresh "
                f"(vehicle fault: {desc})"
            )
        logger.debug(
            "Stale session for %s (%s), retrying with fresh handshake",
            vin,
            command,
        )
        return await self._signed_command(vin, command, body, domain=domain, _retried=True)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_signed_response(
        self,
        data: dict[str, Any],
        vin: str,
        command: str,
        domain: Domain,
    ) -> tuple[CommandResponse | None, MessageFault | None]:
        """Parse a signed_command endpoint response.

        The endpoint returns ``{"response": "<base64-encoded RoutableMessage>"}``.
        Decodes the protobuf, checks for vehicle-side fault codes, and returns
        ``(CommandResponse, None)`` on success.

        Returns ``(None, fault)`` if the fault indicates a stale session — the
        caller should invalidate the session and retry with a fresh handshake.
        """
        response_b64: str = data.get("response", "")
        if not response_b64:
            raise SessionError(f"Empty signed_command response for {vin} ({command})")

        try:
            response_bytes = base64.b64decode(response_b64)
        except Exception as exc:
            raise SessionError(f"Failed to decode signed_command response: {exc}") from exc

        msg = RoutableMessage.parse(response_bytes)
        fault = msg.signed_message_fault

        logger.debug(
            "Signed command '%s' response for %s: fault=%s, has_protobuf_msg=%s, has_signature=%s",
            command,
            vin,
            fault.name,
            bool(msg.protobuf_message_as_bytes),
            msg.signature_data is not None,
        )

        if fault != MessageFault.ERROR_NONE:
            desc = FAULT_DESCRIPTIONS.get(fault, fault.name)

            # Key not enrolled — permanent error, don't retry.
            if fault in KEY_FAULTS:
                raise KeyNotEnrolledError(
                    f"Vehicle rejected command '{command}': {desc}",
                    status_code=422,
                )

            # Stale session — invalidate and signal caller to retry.
            if fault in _STALE_SESSION_FAULTS:
                self._session_mgr.invalidate(vin, domain)
                logger.debug(
                    "Stale session fault %s for %s, invalidated cache",
                    fault.name,
                    vin,
                )
                return None, fault

            # All other faults — raise with descriptive message.
            raise SessionError(
                f"Vehicle rejected command '{command}' for {vin}: {desc} (fault: {fault.name})"
            )

        logger.debug("Signed command '%s' succeeded for %s", command, vin)
        return CommandResponse(response=CommandResult(result=True)), None

    # ------------------------------------------------------------------
    # Named method delegation
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        """Route named command methods through the signed path.

        ``execute_command()`` calls ``getattr(cmd_api, method_name)(vin, **body)``
        — we create wrapper methods that route through ``self._command()``
        which picks the signed or unsigned path based on the command registry.
        """
        spec = get_command_spec(name)
        if spec is not None:
            # Return a wrapper that routes through the signed/unsigned dispatcher
            async def _dispatch(vin: str, **kwargs: Any) -> CommandResponse:
                return await self._command(vin, name, kwargs or None)

            return _dispatch

        # Non-command attributes (e.g. _client) → fall back to unsigned API
        attr = getattr(self._unsigned_api, name, None)
        if attr is not None:
            return attr
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
