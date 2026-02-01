"""Tests for the signed remote_boombox command (VehicleControlRemoteBoomboxAction)."""

from __future__ import annotations

from tescmd.protocol.commands import get_command_spec, requires_signing
from tescmd.protocol.payloads import build_command_payload
from tescmd.protocol.protobuf.messages import Domain

# -- registry ----------------------------------------------------------------


def test_remote_boombox_in_registry() -> None:
    """remote_boombox is registered in the infotainment domain."""
    spec = get_command_spec("remote_boombox")
    assert spec is not None
    assert spec.domain is Domain.DOMAIN_INFOTAINMENT


def test_remote_boombox_requires_signing() -> None:
    """remote_boombox requires signing (no longer routed unsigned)."""
    assert requires_signing("remote_boombox") is True


# -- payload builder ---------------------------------------------------------


def test_boombox_payload_fart() -> None:
    """sound=0 (fart) produces correct protobuf bytes.

    Wire layout:
      Action { field 2 (VehicleAction):
        VehicleAction { field 64 (VehicleControlRemoteBoomboxAction):
          { field 1 (action): varint 0 }
        }
      }
    """
    payload = build_command_payload("remote_boombox", {"sound": 0})
    # inner: varint_field(1, 0) = 0x08 0x00
    # VehicleAction field 64: tag (64<<3|2)=514 → 0x82 0x04, len 2, data
    # Action field 2: tag 0x12, len 5, data
    expected = b"\x12\x05\x82\x04\x02\x08\x00"
    assert payload == expected


def test_boombox_payload_locate() -> None:
    """sound=2000 (locate ping) produces correct protobuf bytes.

    Wire layout:
      Action { field 2 (VehicleAction):
        VehicleAction { field 64 (VehicleControlRemoteBoomboxAction):
          { field 1 (action): varint 2000 }
        }
      }
    """
    payload = build_command_payload("remote_boombox", {"sound": 2000})
    # inner: varint_field(1, 2000) = 0x08, 0xd0, 0x0f
    # VehicleAction field 64: tag 0x82 0x04, len 3, data
    # Action field 2: tag 0x12, len 6, data
    expected = b"\x12\x06\x82\x04\x03\x08\xd0\x0f"
    assert payload == expected


def test_boombox_payload_action_key() -> None:
    """The builder also accepts 'action' as a key (protobuf field name)."""
    payload = build_command_payload("remote_boombox", {"action": 2000})
    expected = build_command_payload("remote_boombox", {"sound": 2000})
    assert payload == expected


def test_boombox_payload_default() -> None:
    """Empty body defaults to action=0 (fart/boombox)."""
    payload = build_command_payload("remote_boombox", {})
    expected = build_command_payload("remote_boombox", {"sound": 0})
    assert payload == expected
