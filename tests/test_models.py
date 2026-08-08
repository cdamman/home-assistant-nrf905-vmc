"""Tests for the per-speed power draw read from the entry options."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.nrf905_vmc.const import (
    CONF_POWER_HIGH,
    CONF_POWER_LOW,
    CONF_POWER_MEDIUM,
    DEFAULT_POWER_BY_SPEED,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
)
from custom_components.nrf905_vmc.models import power_by_speed


def test_no_options_uses_the_defaults() -> None:
    """An entry that was never configured keeps the documented values."""
    assert power_by_speed({}) == DEFAULT_POWER_BY_SPEED
    assert power_by_speed({}) is not DEFAULT_POWER_BY_SPEED  # never share the dict


def test_configured_values_replace_the_defaults() -> None:
    """Every speed can be given its own power draw."""
    assert power_by_speed(
        {CONF_POWER_LOW: 10, CONF_POWER_MEDIUM: 20.5, CONF_POWER_HIGH: 70}
    ) == {SPEED_LOW: 10.0, SPEED_MEDIUM: 20.5, SPEED_HIGH: 70.0}


def test_partial_options_fall_back_per_speed() -> None:
    """Speeds left unconfigured keep their default."""
    assert power_by_speed({CONF_POWER_HIGH: 75.0}) == {
        SPEED_LOW: DEFAULT_POWER_BY_SPEED[SPEED_LOW],
        SPEED_MEDIUM: DEFAULT_POWER_BY_SPEED[SPEED_MEDIUM],
        SPEED_HIGH: 75.0,
    }


@pytest.mark.parametrize("value", ["42", "42.5", 0, 0.0])
def test_values_are_coerced_to_float(value: Any) -> None:
    """Whatever the storage returns is normalised to a float."""
    result = power_by_speed({CONF_POWER_LOW: value})[SPEED_LOW]
    assert isinstance(result, float)
    assert result == float(value)


@pytest.mark.parametrize("value", ["not a number", [], {}, None])
def test_unusable_values_fall_back_to_the_default(value: Any) -> None:
    """A corrupted option never breaks the sensors."""
    assert (
        power_by_speed({CONF_POWER_MEDIUM: value})[SPEED_MEDIUM]
        == DEFAULT_POWER_BY_SPEED[SPEED_MEDIUM]
    )
