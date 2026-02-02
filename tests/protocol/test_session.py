"""Tests for tescmd.protocol.session — SessionManager + handshake fault handling."""

from __future__ import annotations

import base64
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tescmd.api.errors import KeyNotEnrolledError, SessionError, VehicleAsleepError
from tescmd.protocol.protobuf.messages import (
    Domain,
    MessageFault,
    MessageStatus,
    OperationStatus,
    RoutableMessage,
    SessionInfo,
    _encode_fixed32_field,
    _encode_length_delimited,
    _encode_varint_field,
)
from tescmd.protocol.session import _SESSION_TTL, Session, SessionManager

VIN = "5YJ3E1EA1NF000001"


def _build_session_info_response(
    vehicle_key: ec.EllipticCurvePrivateKey,
    *,
    fault: MessageFault = MessageFault.ERROR_NONE,
    include_session_info: bool = True,
) -> dict[str, str]:
    """Build a mock signed_command response with session_info or a fault code."""
    msg = RoutableMessage()

    if fault != MessageFault.ERROR_NONE:
        msg.message_status = MessageStatus(
            operation_status=OperationStatus.OPERATIONSTATUS_ERROR,
            signed_message_fault=fault,
        )

    if include_session_info:
        pub_bytes = vehicle_key.public_key().public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        si = SessionInfo(
            counter=1,
            public_key=pub_bytes,
            epoch=b"\x01\x02\x03\x04",
            clock_time=int(time.time()),
        )
        # Serialize SessionInfo manually (clock_time is fixed32 in the proto)
        si_bytes = b""
        si_bytes += _encode_varint_field(1, si.counter)
        si_bytes += _encode_length_delimited(2, si.public_key)
        si_bytes += _encode_length_delimited(3, si.epoch)
        si_bytes += _encode_fixed32_field(4, si.clock_time)
        msg.session_info = si_bytes

    response_bytes = msg.serialize()
    return {"response": base64.b64encode(response_bytes).decode()}


class TestSessionManagerHandshake:
    """Tests for SessionManager.get_session and handshake."""

    @pytest.mark.asyncio
    async def test_successful_handshake(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """A normal handshake with valid session_info succeeds."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_build_session_info_response(vehicle_key))

        mgr = SessionManager(client_private_key, mock_client)
        session = await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        assert isinstance(session, Session)
        assert session.vin == VIN
        assert session.domain == Domain.DOMAIN_VEHICLE_SECURITY
        assert len(session.shared_key) == 16
        assert len(session.signing_key) == 32
        assert session.epoch == b"\x01\x02\x03\x04"

    @pytest.mark.asyncio
    async def test_session_caching(self, client_private_key: ec.EllipticCurvePrivateKey) -> None:
        """Second call returns cached session without another handshake."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_build_session_info_response(vehicle_key))

        mgr = SessionManager(client_private_key, mock_client)
        s1 = await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)
        s2 = await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        assert s1 is s2
        assert mock_client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_invalidate_clears_cache(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """After invalidate(), next get_session performs a fresh handshake."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_build_session_info_response(vehicle_key))

        mgr = SessionManager(client_private_key, mock_client)
        await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)
        mgr.invalidate(VIN)
        await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        assert mock_client.post.await_count == 2


class TestHandshakeFaultCodes:
    """Tests for fault code handling in the handshake."""

    @pytest.mark.asyncio
    async def test_unknown_key_raises_key_not_enrolled(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """UNKNOWN_KEY_ID fault raises KeyNotEnrolledError immediately."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()
        mock_client.post = AsyncMock(
            return_value=_build_session_info_response(
                vehicle_key,
                fault=MessageFault.ERROR_UNKNOWN_KEY_ID,
                include_session_info=False,
            )
        )

        mgr = SessionManager(client_private_key, mock_client)
        with pytest.raises(KeyNotEnrolledError, match="does not recognize"):
            await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        # Should NOT retry — only 1 call
        assert mock_client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_inactive_key_raises_key_not_enrolled(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """INACTIVE_KEY fault raises KeyNotEnrolledError immediately."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()
        mock_client.post = AsyncMock(
            return_value=_build_session_info_response(
                vehicle_key,
                fault=MessageFault.ERROR_INACTIVE_KEY,
                include_session_info=False,
            )
        )

        mgr = SessionManager(client_private_key, mock_client)
        with pytest.raises(KeyNotEnrolledError, match="disabled"):
            await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

    @pytest.mark.asyncio
    async def test_busy_fault_retries(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """BUSY fault retries and succeeds on second attempt."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()

        busy_response = _build_session_info_response(
            vehicle_key,
            fault=MessageFault.ERROR_BUSY,
            include_session_info=False,
        )
        ok_response = _build_session_info_response(vehicle_key)

        mock_client.post = AsyncMock(side_effect=[busy_response, ok_response])

        mgr = SessionManager(client_private_key, mock_client)
        session = await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        assert isinstance(session, Session)
        assert mock_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_internal_fault_retries(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """INTERNAL fault (vehicle still booting) retries."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()

        internal_response = _build_session_info_response(
            vehicle_key,
            fault=MessageFault.ERROR_INTERNAL,
            include_session_info=False,
        )
        ok_response = _build_session_info_response(vehicle_key)

        mock_client.post = AsyncMock(side_effect=[internal_response, ok_response])

        mgr = SessionManager(client_private_key, mock_client)
        session = await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        assert isinstance(session, Session)
        assert mock_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_transient_fault_exhausts_retries(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """If transient fault persists through all retries, raises SessionError."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()

        busy_response = _build_session_info_response(
            vehicle_key,
            fault=MessageFault.ERROR_BUSY,
            include_session_info=False,
        )
        mock_client.post = AsyncMock(return_value=busy_response)

        mgr = SessionManager(client_private_key, mock_client)
        with pytest.raises(SessionError, match="busy"):
            await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        # Should have retried the max number of times
        assert mock_client.post.await_count == 3

    @pytest.mark.asyncio
    async def test_non_transient_fault_no_retry(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """A non-transient fault (e.g. REMOTE_ACCESS_DISABLED) fails immediately."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()

        response = _build_session_info_response(
            vehicle_key,
            fault=MessageFault.ERROR_REMOTE_ACCESS_DISABLED,
            include_session_info=False,
        )
        mock_client.post = AsyncMock(return_value=response)

        mgr = SessionManager(client_private_key, mock_client)
        with pytest.raises(SessionError, match="Mobile Access"):
            await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        assert mock_client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_http_408_retries_then_propagates(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """HTTP 408 (VehicleAsleepError) retries before propagating."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=VehicleAsleepError("asleep", status_code=408))

        mgr = SessionManager(client_private_key, mock_client)
        with pytest.raises(VehicleAsleepError):
            await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        # Should have retried the max number of times before propagating
        assert mock_client.post.await_count == 3

    @pytest.mark.asyncio
    async def test_http_408_retries_then_succeeds(
        self, client_private_key: ec.EllipticCurvePrivateKey
    ) -> None:
        """HTTP 408 on first attempt, success on second."""
        vehicle_key = ec.generate_private_key(ec.SECP256R1())
        mock_client = MagicMock()

        ok_response = _build_session_info_response(vehicle_key)
        mock_client.post = AsyncMock(
            side_effect=[VehicleAsleepError("asleep", status_code=408), ok_response]
        )

        mgr = SessionManager(client_private_key, mock_client)
        session = await mgr.get_session(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

        assert isinstance(session, Session)
        assert mock_client.post.await_count == 2


class TestSessionExpiry:
    """Tests for session TTL and expiry."""

    def test_session_not_expired(self) -> None:
        session = Session(
            vin=VIN,
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            shared_key=b"\xaa" * 16,
            signing_key=b"\xbb" * 32,
            session_info_key=b"\xcc" * 32,
            epoch=b"\x01\x02\x03\x04",
            counter=0,
            time_zero=time.time(),
            created_at=time.monotonic(),
        )
        assert not session.is_expired

    def test_session_expired(self) -> None:
        session = Session(
            vin=VIN,
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            shared_key=b"\xaa" * 16,
            signing_key=b"\xbb" * 32,
            session_info_key=b"\xcc" * 32,
            epoch=b"\x01\x02\x03\x04",
            counter=0,
            time_zero=time.time(),
            created_at=time.monotonic() - _SESSION_TTL - 1,
        )
        assert session.is_expired

    def test_next_counter_increments(self) -> None:
        session = Session(
            vin=VIN,
            domain=Domain.DOMAIN_VEHICLE_SECURITY,
            shared_key=b"\xaa" * 16,
            signing_key=b"\xbb" * 32,
            session_info_key=b"\xcc" * 32,
            epoch=b"\x01\x02\x03\x04",
            counter=5,
            time_zero=time.time(),
            created_at=time.monotonic(),
        )
        assert session.next_counter() == 6
        assert session.next_counter() == 7
