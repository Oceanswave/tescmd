"""Tests for OpenClaw BridgeConfig."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tescmd.openclaw.config import BridgeConfig, FieldFilter, NodeCapabilities

if TYPE_CHECKING:
    from pathlib import Path


class TestFieldFilter:
    def test_defaults(self) -> None:
        f = FieldFilter()
        assert f.enabled is True
        assert f.granularity == 0.0
        assert f.throttle_seconds == 1.0

    def test_custom_values(self) -> None:
        f = FieldFilter(enabled=False, granularity=50.0, throttle_seconds=5.0)
        assert f.enabled is False
        assert f.granularity == 50.0
        assert f.throttle_seconds == 5.0


class TestBridgeConfigDefaults:
    def test_default_gateway_url(self) -> None:
        cfg = BridgeConfig()
        assert cfg.gateway_url == "ws://127.0.0.1:18789"

    def test_default_client_id(self) -> None:
        cfg = BridgeConfig()
        assert cfg.client_id == "node-host"

    def test_default_token_is_none(self) -> None:
        cfg = BridgeConfig()
        assert cfg.gateway_token is None

    def test_default_filters_populated(self) -> None:
        cfg = BridgeConfig()
        assert "Location" in cfg.telemetry
        assert "Soc" in cfg.telemetry
        assert cfg.telemetry["Location"].granularity == 50.0
        assert cfg.telemetry["Location"].throttle_seconds == 1.0

    def test_default_charge_state_filter(self) -> None:
        cfg = BridgeConfig()
        assert cfg.telemetry["ChargeState"].granularity == 0.0
        assert cfg.telemetry["ChargeState"].throttle_seconds == 0.0


class TestBridgeConfigLoad:
    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = BridgeConfig.load(tmp_path / "nonexistent.json")
        assert cfg.gateway_url == "ws://127.0.0.1:18789"

    def test_load_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bridge.json"
        config_file.write_text(
            json.dumps(
                {
                    "gateway_url": "ws://custom:9999",
                    "gateway_token": "my-token",
                    "client_id": "custom-bridge",
                }
            )
        )
        cfg = BridgeConfig.load(config_file)
        assert cfg.gateway_url == "ws://custom:9999"
        assert cfg.gateway_token == "my-token"
        assert cfg.client_id == "custom-bridge"

    def test_load_preserves_default_filters(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bridge.json"
        config_file.write_text(json.dumps({"gateway_url": "ws://x:1"}))
        cfg = BridgeConfig.load(config_file)
        # Default filters should still be present since telemetry wasn't overridden
        assert "Location" in cfg.telemetry

    def test_load_with_custom_filters(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bridge.json"
        config_file.write_text(
            json.dumps(
                {
                    "telemetry": {
                        "Custom": {"enabled": True, "granularity": 10.0, "throttle_seconds": 2.0}
                    }
                }
            )
        )
        cfg = BridgeConfig.load(config_file)
        assert "Custom" in cfg.telemetry
        assert cfg.telemetry["Custom"].granularity == 10.0


class TestBridgeConfigMerge:
    def test_merge_gateway_url(self) -> None:
        cfg = BridgeConfig()
        merged = cfg.merge_overrides(gateway_url="ws://other:1234")
        assert merged.gateway_url == "ws://other:1234"
        assert cfg.gateway_url == "ws://127.0.0.1:18789"  # original unchanged

    def test_merge_token(self) -> None:
        cfg = BridgeConfig()
        merged = cfg.merge_overrides(gateway_token="secret")
        assert merged.gateway_token == "secret"

    def test_merge_none_keeps_original(self) -> None:
        cfg = BridgeConfig(gateway_url="ws://keep:1")
        merged = cfg.merge_overrides(gateway_url=None)
        assert merged.gateway_url == "ws://keep:1"


class TestNodeCapabilities:
    def test_defaults(self) -> None:
        caps = NodeCapabilities()
        assert "location.get" in caps.reads
        assert "battery.get" in caps.reads
        assert "door.lock" in caps.writes
        assert "flash_lights" in caps.writes

    def test_custom_reads(self) -> None:
        caps = NodeCapabilities(reads=["custom.read"])
        assert caps.reads == ["custom.read"]
        # writes should still be default
        assert len(caps.writes) > 0

    def test_custom_writes(self) -> None:
        caps = NodeCapabilities(writes=["custom.write"])
        assert caps.writes == ["custom.write"]

    def test_from_dict(self) -> None:
        caps = NodeCapabilities.model_validate({"reads": ["a.get", "b.get"], "writes": ["c.do"]})
        assert caps.reads == ["a.get", "b.get"]
        assert caps.writes == ["c.do"]

    def test_to_connect_params(self) -> None:
        caps = NodeCapabilities(reads=["location.get", "battery.get"], writes=["door.lock"])
        params = caps.to_connect_params()
        assert params["caps"] == ["location", "battery", "door"]
        assert params["commands"] == ["location.get", "battery.get", "door.lock"]
        assert params["permissions"] == {
            "location.get": True,
            "battery.get": True,
            "door.lock": True,
        }

    def test_caps_deduplicates_domains(self) -> None:
        caps = NodeCapabilities(reads=["door.status"], writes=["door.lock", "door.unlock"])
        assert caps.caps == ["door"]

    def test_all_commands_preserves_order(self) -> None:
        caps = NodeCapabilities(reads=["a.get"], writes=["b.do", "a.get"])
        # a.get appears in both reads and writes — deduplicated, reads-first order
        assert caps.all_commands == ["a.get", "b.do"]


class TestBridgeConfigCapabilities:
    def test_default_capabilities(self) -> None:
        cfg = BridgeConfig()
        assert isinstance(cfg.capabilities, NodeCapabilities)
        assert len(cfg.capabilities.reads) == 8
        assert len(cfg.capabilities.writes) == 21

    def test_custom_capabilities_from_json(self, tmp_path: Path) -> None:
        config_file = tmp_path / "bridge.json"
        config_file.write_text(
            json.dumps(
                {
                    "capabilities": {
                        "reads": ["location.get"],
                        "writes": ["door.lock"],
                    }
                }
            )
        )
        cfg = BridgeConfig.load(config_file)
        assert cfg.capabilities.reads == ["location.get"]
        assert cfg.capabilities.writes == ["door.lock"]

    def test_serialization_includes_capabilities(self) -> None:
        cfg = BridgeConfig()
        data = cfg.model_dump()
        assert "capabilities" in data
        assert "reads" in data["capabilities"]
        assert "writes" in data["capabilities"]

    def test_merge_preserves_capabilities(self) -> None:
        cfg = BridgeConfig(
            capabilities=NodeCapabilities(reads=["custom.get"], writes=["custom.do"])
        )
        merged = cfg.merge_overrides(gateway_url="ws://other:1234")
        assert merged.capabilities.reads == ["custom.get"]
        assert merged.capabilities.writes == ["custom.do"]
