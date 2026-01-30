"""Tests for tescmd._internal.vin — VIN validation and resolution."""

from __future__ import annotations

import os

import pytest

from tescmd._internal.vin import InvalidVINError, resolve_vin, validate_vin


class TestValidateVin:
    def test_valid_vin_passes(self) -> None:
        result = validate_vin("5YJ3E1EA1NF000001")
        assert result == "5YJ3E1EA1NF000001"

    def test_lowercase_is_uppercased(self) -> None:
        result = validate_vin("5yj3e1ea1nf000001")
        assert result == "5YJ3E1EA1NF000001"

    def test_too_short_vin_fails(self) -> None:
        with pytest.raises(InvalidVINError, match="Invalid VIN"):
            validate_vin("5YJ3E1EA1NF0000")

    def test_too_long_vin_fails(self) -> None:
        with pytest.raises(InvalidVINError, match="Invalid VIN"):
            validate_vin("5YJ3E1EA1NF0000012")

    def test_vin_with_letter_i_fails(self) -> None:
        with pytest.raises(InvalidVINError, match="Invalid VIN"):
            validate_vin("5YJ3E1EA1NI000001")

    def test_vin_with_letter_o_fails(self) -> None:
        with pytest.raises(InvalidVINError, match="Invalid VIN"):
            validate_vin("5YJ3E1EA1NO000001")

    def test_vin_with_letter_q_fails(self) -> None:
        with pytest.raises(InvalidVINError, match="Invalid VIN"):
            validate_vin("5YJ3E1EA1NQ000001")

    def test_empty_vin_fails(self) -> None:
        with pytest.raises(InvalidVINError, match="Invalid VIN"):
            validate_vin("")

    def test_vin_with_special_characters_fails(self) -> None:
        with pytest.raises(InvalidVINError, match="Invalid VIN"):
            validate_vin("5YJ3E1EA1NF00000!")


class TestResolveVin:
    def test_positional_takes_priority(self) -> None:
        result = resolve_vin(vin_positional="POS", vin_flag="FLAG")
        assert result == "POS"

    def test_flag_used_when_no_positional(self) -> None:
        result = resolve_vin(vin_flag="FLAG")
        assert result == "FLAG"

    def test_env_used_when_no_positional_or_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TESLA_VIN", "ENVVIN")
        result = resolve_vin()
        assert result == "ENVVIN"

    def test_returns_none_when_no_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TESLA_VIN", raising=False)
        result = resolve_vin()
        assert result is None
