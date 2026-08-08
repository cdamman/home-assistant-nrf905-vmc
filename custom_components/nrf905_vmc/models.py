"""Runtime data model shared between platforms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .api import Nrf905Api
from .const import DEFAULT_POWER_BY_SPEED, POWER_OPTION_BY_SPEED
from .coordinator import Nrf905Coordinator


def power_by_speed(options: Mapping[str, Any]) -> dict[str, float]:
    """Return the power draw (W) of each speed from the entry options.

    Speeds the user has not configured keep the default of the unit this
    integration was written against.
    """
    result: dict[str, float] = {}
    for speed, key in POWER_OPTION_BY_SPEED.items():
        value = options.get(key)
        try:
            result[speed] = (
                DEFAULT_POWER_BY_SPEED[speed] if value is None else float(value)
            )
        except (TypeError, ValueError):
            result[speed] = DEFAULT_POWER_BY_SPEED[speed]
    return result


@dataclass
class Nrf905Runtime:
    """Data kept alive for the lifetime of a config entry.

    ``timer_minutes`` is the live value driven by the number entity; the fan
    uses it as the auto-revert delay when the "on" command boosts to high, and
    the remaining-timer sensor uses it as the countdown length.

    ``power_by_speed`` holds the configured power draw of each speed, used by
    the power and daily-energy sensors.
    """

    api: Nrf905Api
    coordinator: Nrf905Coordinator
    timer_minutes: int
    power_by_speed: dict[str, float]


Nrf905ConfigEntry = ConfigEntry[Nrf905Runtime]
