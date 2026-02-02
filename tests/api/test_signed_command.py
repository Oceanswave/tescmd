"""Tests for tescmd.api.signed_command — SignedCommandAPI."""

from __future__ import annotations

import base64
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from tescmd.api.errors import KeyNotEnrolledError, SessionError, TeslaAPIError
from tescmd.api.signed_command import SignedCommandAPI
from tescmd.models.command import CommandResponse
from tescmd.protocol.protobuf.messages import (
    Domain,
    MessageFault,
    MessageStatus,
    OperationStatus,
    RoutableMessage,
)
from tescmd.protocol.session import Session

VIN = "5YJ3E1EA1NF000001"

# REST-format OK response — used only for the unsigned fallback path.
_OK_RESPONSE = {"response": {"result": True, "reason": ""}}


def _build_signed_ok_response() -> dict[str, str]:
    """Build a mock signed_command success response (base64-encoded RoutableMessage)."""
    msg = RoutableMessage()
    msg.uuid = b"\x00" * 16
    return {"response": base64.b64encode(msg.serialize()).decode()}


def _build_signed_fault_response(fault: MessageFault) -> dict[str, str]:
    """Build a mock signed_command response with a specific fault code."""
    msg = RoutableMessage()
    msg.uuid = b"\x00" * 16
    msg.message_status = MessageStatus(
        operation_status=OperationStatus.OPERATIONSTATUS_ERROR,
        signed_message_fault=fault,
    )
    return {"response": base64.b64encode(msg.serialize()).decode()}


@pytest.fixture
def mock_session() -> Session:
    """Return a mock ECDH session with deterministic keys."""
    return Session(
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


@pytest.fixture
def mock_session_mgr(mock_session: Session) -> MagicMock:
    """Return a mock SessionManager that yields the mock session."""
    mgr = MagicMock()
    mgr.get_session = AsyncMock(return_value=mock_session)
    mgr.client_public_key = b"\x04" + b"\xdd" * 64  # 65-byte uncompressed EC point
    return mgr


@pytest.fixture
def mock_unsigned_api() -> MagicMock:
    """Return a mock CommandAPI used as the unsigned fallback."""
    api = MagicMock()
    api._command = AsyncMock(return_value=CommandResponse.model_validate(_OK_RESPONSE))
    return api


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a mock TeslaFleetClient with an async post method."""
    client = MagicMock()
    client.post = AsyncMock(return_value=_build_signed_ok_response())
    return client


@pytest.fixture
def signed_api(
    mock_client: MagicMock,
    mock_session_mgr: MagicMock,
    mock_unsigned_api: MagicMock,
) -> SignedCommandAPI:
    """Return a SignedCommandAPI wired with all mocks."""
    return SignedCommandAPI(mock_client, mock_session_mgr, mock_unsigned_api)


class TestSignedCommandAPI:
    """Tests for SignedCommandAPI routing, signing, and delegation."""

    @pytest.mark.asyncio
    async def test_unsigned_command_delegates(
        self,
        signed_api: SignedCommandAPI,
        mock_unsigned_api: MagicMock,
    ) -> None:
        """wake_up (requires_signing=False) delegates to unsigned_api._command."""
        result = await signed_api._command(VIN, "wake_up")

        mock_unsigned_api._command.assert_awaited_once_with(VIN, "wake_up", None)
        assert isinstance(result, CommandResponse)
        assert result.response.result is True

    @pytest.mark.asyncio
    async def test_signed_command_posts_to_signed_endpoint(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
    ) -> None:
        """door_lock (VCSEC, signed) posts to /api/1/vehicles/{vin}/signed_command."""
        await signed_api._command(VIN, "door_lock")

        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == f"/api/1/vehicles/{VIN}/signed_command"

    @pytest.mark.asyncio
    async def test_signed_command_includes_routable_message(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
    ) -> None:
        """The POST body contains a 'routable_message' key with a base64-encoded string."""
        await signed_api._command(VIN, "door_lock")

        call_args = mock_client.post.call_args
        json_body = call_args[1]["json"]
        assert "routable_message" in json_body

        # Verify the value is valid base64
        encoded = json_body["routable_message"]
        assert isinstance(encoded, str)
        decoded = base64.b64decode(encoded)
        assert len(decoded) > 0

    @pytest.mark.asyncio
    async def test_signed_command_increments_counter(
        self,
        signed_api: SignedCommandAPI,
        mock_session: Session,
    ) -> None:
        """session.next_counter() is called, incrementing the anti-replay counter."""
        initial_counter = mock_session.counter
        await signed_api._command(VIN, "door_lock")

        # next_counter() should have been called, incrementing counter from 0 to 1
        assert mock_session.counter == initial_counter + 1

    @pytest.mark.asyncio
    async def test_unknown_command_delegates_to_unsigned(
        self,
        signed_api: SignedCommandAPI,
        mock_unsigned_api: MagicMock,
    ) -> None:
        """A command not in the registry falls through to unsigned_api._command."""
        await signed_api._command(VIN, "some_unknown_command_xyz")

        mock_unsigned_api._command.assert_awaited_once_with(VIN, "some_unknown_command_xyz", None)

    @pytest.mark.asyncio
    async def test_key_not_enrolled_error(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
    ) -> None:
        """'not enrolled' in API error → KeyNotEnrolledError."""
        mock_client.post = AsyncMock(
            side_effect=TeslaAPIError("vehicle key not enrolled for this command", status_code=422)
        )

        with pytest.raises(KeyNotEnrolledError, match="Key not enrolled"):
            await signed_api._command(VIN, "door_lock")

    def test_getattr_returns_dispatch_for_registered_commands(
        self,
        signed_api: SignedCommandAPI,
        mock_unsigned_api: MagicMock,
    ) -> None:
        """getattr(api, 'charge_start') returns a dispatch wrapper, not the unsigned API method."""
        mock_unsigned_api.charge_start = MagicMock(name="charge_start")

        attr = signed_api.charge_start

        # Registered commands return a dispatch function that routes through _command()
        assert callable(attr)
        assert attr is not mock_unsigned_api.charge_start

    def test_getattr_raises_for_missing_attribute(
        self,
        mock_client: MagicMock,
        mock_session_mgr: MagicMock,
    ) -> None:
        """Accessing a nonexistent attribute raises AttributeError."""
        # Use a spec-limited mock so unknown attributes are not auto-created
        unsigned = MagicMock(spec=[])
        api = SignedCommandAPI(mock_client, mock_session_mgr, unsigned)

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = api.totally_nonexistent_attribute_xyz


class TestSignedResponseParsing:
    """Tests for _parse_signed_response and stale session retry."""

    @pytest.mark.asyncio
    async def test_success_response_returns_command_response(
        self,
        signed_api: SignedCommandAPI,
    ) -> None:
        """A fault-free RoutableMessage produces CommandResponse(result=True)."""
        result = await signed_api._command(VIN, "door_lock")
        assert isinstance(result, CommandResponse)
        assert result.response.result is True

    @pytest.mark.asyncio
    async def test_key_fault_raises_key_not_enrolled(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
    ) -> None:
        """UNKNOWN_KEY_ID fault in protobuf response raises KeyNotEnrolledError."""
        mock_client.post = AsyncMock(
            return_value=_build_signed_fault_response(MessageFault.ERROR_UNKNOWN_KEY_ID)
        )
        with pytest.raises(KeyNotEnrolledError, match="does not recognize"):
            await signed_api._command(VIN, "door_lock")

    @pytest.mark.asyncio
    async def test_stale_session_retries_once(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
        mock_session_mgr: MagicMock,
    ) -> None:
        """INCORRECT_EPOCH → invalidate session + retry once with fresh handshake."""
        stale_response = _build_signed_fault_response(MessageFault.ERROR_INCORRECT_EPOCH)
        ok_response = _build_signed_ok_response()
        mock_client.post = AsyncMock(side_effect=[stale_response, ok_response])

        result = await signed_api._command(VIN, "door_lock")

        assert isinstance(result, CommandResponse)
        assert result.response.result is True
        # Should have been called twice: original + retry
        assert mock_client.post.await_count == 2
        # Session should have been invalidated after the first (stale) response
        mock_session_mgr.invalidate.assert_called_once_with(VIN, Domain.DOMAIN_VEHICLE_SECURITY)

    @pytest.mark.asyncio
    async def test_stale_session_gives_up_after_one_retry(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
    ) -> None:
        """If the second attempt also returns a stale fault, raise SessionError."""
        stale_response = _build_signed_fault_response(MessageFault.ERROR_INCORRECT_EPOCH)
        mock_client.post = AsyncMock(return_value=stale_response)

        with pytest.raises(SessionError, match="after session refresh"):
            await signed_api._command(VIN, "door_lock")

        assert mock_client.post.await_count == 2

    @pytest.mark.asyncio
    async def test_non_stale_non_key_fault_raises_session_error(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
    ) -> None:
        """A non-transient, non-key fault (e.g. INVALID_COMMAND) raises SessionError."""
        mock_client.post = AsyncMock(
            return_value=_build_signed_fault_response(MessageFault.ERROR_INVALID_COMMAND)
        )
        with pytest.raises(SessionError, match="Unrecognized command"):
            await signed_api._command(VIN, "door_lock")

        # Should NOT retry — only 1 call
        assert mock_client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_empty_response_raises_session_error(
        self,
        signed_api: SignedCommandAPI,
        mock_client: MagicMock,
    ) -> None:
        """An empty 'response' field raises SessionError."""
        mock_client.post = AsyncMock(return_value={"response": ""})
        with pytest.raises(SessionError, match="Empty signed_command response"):
            await signed_api._command(VIN, "door_lock")
