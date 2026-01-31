"""Tests for the command registry (tescmd.protocol.commands)."""

from __future__ import annotations

import pytest

from tescmd.protocol.commands import (
    COMMAND_REGISTRY,
    CommandSpec,
    get_command_spec,
    get_domain,
    requires_signing,
)
from tescmd.protocol.protobuf.messages import Domain

# -- get_command_spec ---------------------------------------------------------


def test_get_command_spec_vcsec() -> None:
    """door_lock returns a spec with DOMAIN_VEHICLE_SECURITY."""
    spec = get_command_spec("door_lock")
    assert spec is not None
    assert isinstance(spec, CommandSpec)
    assert spec.domain is Domain.DOMAIN_VEHICLE_SECURITY


def test_get_command_spec_infotainment() -> None:
    """charge_start returns a spec with DOMAIN_INFOTAINMENT."""
    spec = get_command_spec("charge_start")
    assert spec is not None
    assert isinstance(spec, CommandSpec)
    assert spec.domain is Domain.DOMAIN_INFOTAINMENT


def test_get_command_spec_unsigned() -> None:
    """wake_up returns a spec with DOMAIN_BROADCAST and requires_signing=False."""
    spec = get_command_spec("wake_up")
    assert spec is not None
    assert spec.domain is Domain.DOMAIN_BROADCAST
    assert spec.requires_signing is False


def test_get_command_spec_unknown() -> None:
    """A nonexistent command returns None."""
    assert get_command_spec("totally_fake_command") is None


# -- get_domain ---------------------------------------------------------------


def test_get_domain_vcsec() -> None:
    """door_lock maps to DOMAIN_VEHICLE_SECURITY."""
    assert get_domain("door_lock") is Domain.DOMAIN_VEHICLE_SECURITY


def test_get_domain_infotainment() -> None:
    """auto_conditioning_start maps to DOMAIN_INFOTAINMENT."""
    assert get_domain("auto_conditioning_start") is Domain.DOMAIN_INFOTAINMENT


def test_get_domain_unknown() -> None:
    """A nonexistent command returns None."""
    assert get_domain("totally_fake_command") is None


# -- requires_signing ---------------------------------------------------------


def test_requires_signing_true() -> None:
    """door_lock requires signing."""
    assert requires_signing("door_lock") is True


def test_requires_signing_false() -> None:
    """wake_up does not require signing."""
    assert requires_signing("wake_up") is False


def test_requires_signing_unknown() -> None:
    """An unknown command defaults to False (unsigned fallback)."""
    assert requires_signing("totally_fake_command") is False


# -- action_type --------------------------------------------------------------


def test_action_type_lock() -> None:
    """door_lock has action_type 'RKE_ACTION_LOCK'."""
    spec = get_command_spec("door_lock")
    assert spec is not None
    assert spec.action_type == "RKE_ACTION_LOCK"


def test_action_type_unlock() -> None:
    """door_unlock has action_type 'RKE_ACTION_UNLOCK'."""
    spec = get_command_spec("door_unlock")
    assert spec is not None
    assert spec.action_type == "RKE_ACTION_UNLOCK"


# -- registry coverage --------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "charge_start",
        "charge_stop",
        "set_temps",
        "set_sentry_mode",
        "honk_horn",
    ],
)
def test_registry_has_common_commands(command: str) -> None:
    """Common infotainment commands are present in COMMAND_REGISTRY."""
    assert command in COMMAND_REGISTRY
    spec = COMMAND_REGISTRY[command]
    assert isinstance(spec, CommandSpec)
    assert spec.domain is Domain.DOMAIN_INFOTAINMENT
