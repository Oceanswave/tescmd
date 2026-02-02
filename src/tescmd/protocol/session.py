"""ECDH session management for the Vehicle Command Protocol.

Manages per-(VIN, domain) ECDH sessions with in-memory caching,
counter management, and automatic re-handshake on expiry.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tescmd.api.errors import (
    KeyNotEnrolledError,
    SessionError,
    TeslaAPIError,
    VehicleAsleepError,
)
from tescmd.crypto.ecdh import derive_session_key, get_uncompressed_public_key
from tescmd.protocol.encoder import build_session_info_request, encode_routable_message
from tescmd.protocol.protobuf.messages import (
    FAULT_DESCRIPTIONS,
    KEY_FAULTS,
    TRANSIENT_FAULTS,
    Domain,
    MessageFault,
    RoutableMessage,
    SessionInfo,
)
from tescmd.protocol.signer import (
    derive_session_info_key,
    derive_signing_key,
    verify_session_info_tag,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import ec

    from tescmd.api.client import TeslaFleetClient

# Default session TTL (5 minutes)
_SESSION_TTL = 300

# Retry config for transient handshake faults (BUSY, TIMEOUT, INTERNAL).
# The vehicle's VCSEC subsystem needs time to boot after waking.
_HANDSHAKE_MAX_RETRIES = 3
_HANDSHAKE_RETRY_DELAY = 3.0  # seconds between retries


@dataclass
class Session:
    """An active ECDH session with a vehicle for a specific domain."""

    vin: str
    domain: Domain
    shared_key: bytes
    signing_key: bytes
    session_info_key: bytes
    epoch: bytes
    counter: int
    time_zero: float  # wall-clock time when the vehicle's epoch counter was 0
    created_at: float
    ttl: float = _SESSION_TTL

    @property
    def is_expired(self) -> bool:
        return time.monotonic() - self.created_at > self.ttl

    def next_counter(self) -> int:
        """Return and increment the anti-replay counter.

        This is safe because all callers run on the same asyncio event
        loop and ``next_counter`` is synchronous — no ``await`` between
        the read and the increment means no interleaving is possible.
        """
        self.counter += 1
        return self.counter


class SessionManager:
    """Manages ECDH sessions per (VIN, domain).

    Usage::

        mgr = SessionManager(private_key, client)
        session = await mgr.get_session(vin, Domain.DOMAIN_INFOTAINMENT)
        # session.signing_key, session.epoch, session.counter, ...
    """

    def __init__(
        self,
        private_key: ec.EllipticCurvePrivateKey,
        client: TeslaFleetClient,
    ) -> None:
        self._private_key = private_key
        self._client = client
        self._client_public_key = get_uncompressed_public_key(private_key)
        self._sessions: dict[tuple[str, Domain], Session] = {}

    @property
    def client_public_key(self) -> bytes:
        return self._client_public_key

    async def get_session(self, vin: str, domain: Domain) -> Session:
        """Return a valid session, performing a handshake if needed."""
        key = (vin, domain)
        session = self._sessions.get(key)
        if session is not None:
            if not session.is_expired:
                return session
            del self._sessions[key]

        session = await self._handshake(vin, domain)
        self._sessions[key] = session
        return session

    def invalidate(self, vin: str, domain: Domain | None = None) -> None:
        """Invalidate cached sessions for a VIN (optionally for a specific domain)."""
        if domain is not None:
            self._sessions.pop((vin, domain), None)
        else:
            for key in list(self._sessions):
                if key[0] == vin:
                    del self._sessions[key]

    async def _handshake(self, vin: str, domain: Domain) -> Session:
        """Perform ECDH handshake with the vehicle.

        1. Build RoutableMessage with session_info_request
        2. POST to /api/1/vehicles/{vin}/signed_command
        3. Check for fault codes — retry transient faults (BUSY/TIMEOUT/INTERNAL)
        4. Parse vehicle's SessionInfo response
        5. ECDH → derive shared key
        6. Validate response HMAC
        7. Store session
        """
        last_fault: MessageFault | None = None

        for attempt in range(1, _HANDSHAKE_MAX_RETRIES + 1):
            # HTTP 408 from the signed_command endpoint means the vehicle's
            # subsystem (VCSEC/Infotainment) didn't respond within the API
            # server's timeout window — NOT necessarily that the vehicle is
            # asleep.  Retry it like a transient protobuf fault.
            try:
                response_msg = await self._send_handshake(vin, domain)
            except VehicleAsleepError:
                if attempt < _HANDSHAKE_MAX_RETRIES:
                    logger.debug(
                        "Handshake HTTP 408 for %s (%s), retry %d/%d",
                        vin,
                        domain.name,
                        attempt,
                        _HANDSHAKE_MAX_RETRIES,
                    )
                    await asyncio.sleep(_HANDSHAKE_RETRY_DELAY)
                    continue
                # Exhausted retries — re-raise so auto_wake() can handle
                # genuinely asleep vehicles.
                raise

            # Check for vehicle-side fault before looking at session_info.
            fault = response_msg.signed_message_fault
            logger.debug(
                "Handshake parsed for %s (%s): fault=%s, has_session_info=%s, "
                "has_protobuf_msg=%s, has_signature=%s",
                vin,
                domain.name,
                fault.name,
                bool(response_msg.session_info),
                bool(response_msg.protobuf_message_as_bytes),
                response_msg.signature_data is not None,
            )
            if fault != MessageFault.ERROR_NONE:
                desc = FAULT_DESCRIPTIONS.get(fault, fault.name)
                last_fault = fault

                # Key not recognized → permanent error, don't retry.
                if fault in KEY_FAULTS:
                    raise KeyNotEnrolledError(
                        f"Vehicle rejected handshake: {desc}",
                        status_code=422,
                    )

                # Transient fault → retry after delay.
                if fault in TRANSIENT_FAULTS and attempt < _HANDSHAKE_MAX_RETRIES:
                    logger.debug(
                        "Handshake fault %s for %s (%s), retry %d/%d",
                        fault.name,
                        vin,
                        domain.name,
                        attempt,
                        _HANDSHAKE_MAX_RETRIES,
                    )
                    await asyncio.sleep(_HANDSHAKE_RETRY_DELAY)
                    continue

                # Non-transient or exhausted retries.
                raise SessionError(f"Vehicle rejected handshake for {vin} ({domain.name}): {desc}")

            if not response_msg.session_info:
                raise SessionError(
                    f"No session_info in handshake response for {vin} ({domain.name})"
                )

            return self._build_session(vin, domain, response_msg)

        # Should not be reached, but handle exhausted retries with last fault.
        desc = FAULT_DESCRIPTIONS.get(last_fault, str(last_fault)) if last_fault else "unknown"
        raise SessionError(
            f"Handshake failed after {_HANDSHAKE_MAX_RETRIES} attempts "
            f"for {vin} ({domain.name}): {desc}"
        )

    async def _send_handshake(self, vin: str, domain: Domain) -> RoutableMessage:
        """Send a session_info_request and return the parsed response."""
        request_msg = build_session_info_request(
            domain=domain,
            client_public_key=self._client_public_key,
        )
        encoded = encode_routable_message(request_msg)
        logger.debug(
            "Sending handshake for %s (%s): %d bytes encoded, pub_key=%d bytes",
            vin,
            domain.name,
            len(encoded),
            len(self._client_public_key),
        )

        try:
            response_data = await self._client.post(
                f"/api/1/vehicles/{vin}/signed_command",
                json={"routable_message": encoded},
            )
        except TeslaAPIError:
            # Let domain-specific errors (VehicleAsleepError, RateLimitError,
            # etc.) propagate so callers like auto_wake() can handle them.
            raise
        except Exception as exc:
            raise SessionError(
                f"Session handshake failed for {vin} ({domain.name}): {exc}"
            ) from exc

        response_b64: str = response_data.get("response", "")
        if not response_b64:
            logger.debug(
                "Empty handshake response for %s (%s): %r",
                vin,
                domain.name,
                response_data,
            )
            raise SessionError(f"Empty session handshake response for {vin} ({domain.name})")

        try:
            response_bytes = base64.b64decode(response_b64)
        except Exception as exc:
            raise SessionError(f"Failed to decode handshake response: {exc}") from exc

        logger.debug(
            "Handshake response for %s (%s): %d bytes, hex=%s",
            vin,
            domain.name,
            len(response_bytes),
            response_bytes.hex(),
        )

        try:
            return RoutableMessage.parse(response_bytes)
        except Exception as exc:
            raise SessionError(f"Failed to parse handshake response: {exc}") from exc

    def _build_session(self, vin: str, domain: Domain, response_msg: RoutableMessage) -> Session:
        """Derive keys and build a Session from a successful handshake response."""
        session_info = SessionInfo.parse(response_msg.session_info)
        if not session_info.public_key:
            raise SessionError(f"No vehicle public key in session info for {vin} ({domain.name})")

        # ECDH key derivation
        try:
            shared_key = derive_session_key(self._private_key, session_info.public_key)
        except Exception as exc:
            raise SessionError(
                f"ECDH key derivation failed for {vin} ({domain.name}): {exc}"
            ) from exc

        # Derive sub-keys
        signing_key = derive_signing_key(shared_key)
        session_info_key = derive_session_info_key(shared_key)

        # Verify session info HMAC tag (if present in response)
        sig = response_msg.signature_data
        si_tag = sig.session_info_tag if sig else None
        if (
            si_tag
            and si_tag.tag
            and not verify_session_info_tag(
                session_info_key,
                response_msg.session_info,
                si_tag.tag,
            )
        ):
            raise SessionError(
                f"Session info HMAC verification failed for {vin} ({domain.name}). "
                "The vehicle response may have been tampered with."
            )

        # Reconstruct the wall-clock instant when the vehicle's epoch counter
        # was zero.  The Go SDK does: timeZero = now - Duration(clockTime).
        # clock_time is a monotonic uptime counter (seconds since the
        # vehicle's security module last booted), NOT a Unix timestamp.
        now = time.time()
        time_zero = now - session_info.clock_time if session_info.clock_time else now

        return Session(
            vin=vin,
            domain=domain,
            shared_key=shared_key,
            signing_key=signing_key,
            session_info_key=session_info_key,
            epoch=session_info.epoch,
            counter=session_info.counter,
            time_zero=time_zero,
            created_at=time.monotonic(),
        )
