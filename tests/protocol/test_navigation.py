"""Tests for navigation command payload builders.

Proto definitions from Teslemetry's extended car_server.proto:
  NavigationRequest (VehicleAction field 21)
  NavigationSuperchargerRequest (VehicleAction field 22)
  NavigationGpsRequest (VehicleAction field 53)
  NavigationWaypointsRequest (VehicleAction field 90)
"""

from __future__ import annotations

import struct

from tescmd.protocol.commands import get_command_spec, requires_signing
from tescmd.protocol.payloads import build_command_payload
from tescmd.protocol.protobuf.messages import Domain

# -- registry ----------------------------------------------------------------


def test_share_in_registry() -> None:
    """share is registered in the infotainment domain with signing required."""
    spec = get_command_spec("share")
    assert spec is not None
    assert spec.domain is Domain.DOMAIN_INFOTAINMENT
    assert spec.requires_signing is True


def test_navigation_gps_requires_signing() -> None:
    assert requires_signing("navigation_gps_request") is True


def test_navigation_sc_requires_signing() -> None:
    assert requires_signing("navigation_sc_request") is True


def test_navigation_waypoints_requires_signing() -> None:
    assert requires_signing("navigation_waypoints_request") is True


# -- share / NavigationRequest (field 21) ------------------------------------


def test_share_payload_address() -> None:
    """share with address builds NavigationRequest { destination="Home" }."""
    payload = build_command_payload("share", {"address": "Home"})
    # Inner: length_delimited(1, b"Home") = 0x0a 0x04 "Home"
    # VehicleAction field 21: tag = (21<<3|2) = 0xaa 0x01, len, data
    # Action field 2: tag 0x12, len, data
    assert payload is not None
    assert len(payload) > 0
    # Verify the destination "Home" is encoded in the output
    assert b"Home" in payload


def test_share_payload_with_order() -> None:
    """share with address and order includes both fields."""
    payload = build_command_payload("share", {"address": "Work", "order": 1})
    assert b"Work" in payload
    # Order field should also be present (varint encoding of 1)
    no_order = build_command_payload("share", {"address": "Work"})
    assert len(payload) > len(no_order)


def test_share_payload_destination_key() -> None:
    """Builder also accepts 'destination' as key (proto field name)."""
    by_address = build_command_payload("share", {"address": "123 Main St"})
    by_dest = build_command_payload("share", {"destination": "123 Main St"})
    assert by_address == by_dest


def test_share_payload_empty_body() -> None:
    """Empty body produces a valid (minimal) NavigationRequest."""
    payload = build_command_payload("share", {})
    assert payload is not None
    assert len(payload) > 0


# -- NavigationGpsRequest (field 53) -----------------------------------------


def test_gps_payload_lat_lon() -> None:
    """GPS request encodes lat/lon as doubles."""
    payload = build_command_payload(
        "navigation_gps_request", {"lat": 37.7749, "lon": -122.4194}
    )
    assert payload is not None
    # Verify the doubles are present in the binary output
    lat_bytes = struct.pack("<d", 37.7749)
    lon_bytes = struct.pack("<d", -122.4194)
    assert lat_bytes in payload
    assert lon_bytes in payload


def test_gps_payload_with_order() -> None:
    """GPS request with order includes the enum field."""
    without_order = build_command_payload(
        "navigation_gps_request", {"lat": 37.0, "lon": -122.0}
    )
    with_order = build_command_payload(
        "navigation_gps_request", {"lat": 37.0, "lon": -122.0, "order": 1}
    )
    assert len(with_order) > len(without_order)


def test_gps_payload_zero_coords() -> None:
    """GPS request handles 0,0 coordinates."""
    payload = build_command_payload("navigation_gps_request", {"lat": 0.0, "lon": 0.0})
    assert payload is not None
    assert len(payload) > 0


# -- NavigationSuperchargerRequest (field 22) --------------------------------


def test_sc_payload_default_order() -> None:
    """Supercharger request defaults to order=1."""
    payload = build_command_payload("navigation_sc_request", {})
    assert payload is not None
    assert len(payload) > 0


def test_sc_payload_custom_order() -> None:
    """Supercharger request with custom order."""
    p1 = build_command_payload("navigation_sc_request", {"order": 1})
    p2 = build_command_payload("navigation_sc_request", {"order": 2})
    assert p1 != p2


# -- NavigationWaypointsRequest (field 90) -----------------------------------


def test_waypoints_payload() -> None:
    """Waypoints request encodes the waypoints string."""
    wps = "refId:ChIJIQBpAG2ahYAR_6128GcTUEo,refId:ChIJw____96GhYARCVVwg5cT7c0"
    payload = build_command_payload("navigation_waypoints_request", {"waypoints": wps})
    assert payload is not None
    # The waypoints string should appear in the binary output (as UTF-8)
    assert b"refId:ChIJIQBpAG2ahYAR_6128GcTUEo" in payload


def test_waypoints_payload_empty() -> None:
    """Empty waypoints string produces a valid (minimal) payload."""
    payload = build_command_payload("navigation_waypoints_request", {})
    assert payload is not None
    assert len(payload) > 0
