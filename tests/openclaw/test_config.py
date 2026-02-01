"""Tests for OpenClaw BridgeConfig."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tescmd.openclaw.config import BridgeConfig, FieldFilter

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
        assert cfg.client_id == "tescmd-bridge"

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
