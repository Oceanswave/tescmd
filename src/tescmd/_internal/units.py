"""Unit conversion helpers shared across the codebase."""

from __future__ import annotations


def fahrenheit_to_celsius(f: float) -> float:
    """Convert Fahrenheit to Celsius, rounded to 1 decimal place."""
    return round((f - 32.0) * 5.0 / 9.0, 1)


def celsius_to_fahrenheit(c: float) -> float:
    """Convert Celsius to Fahrenheit, rounded to 1 decimal place."""
    return round(c * 9.0 / 5.0 + 32.0, 1)
