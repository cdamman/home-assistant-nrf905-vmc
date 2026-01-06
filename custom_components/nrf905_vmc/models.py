"""Runtime data model shared between platforms."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .api import Nrf905Api
from .coordinator import Nrf905Coordinator


@dataclass
class Nrf905Runtime:
    """Data kept alive for the lifetime of a config entry.

    ``timer_minutes`` is the live value driven by the number entity; the fan
    uses it as the auto-revert delay when the "on" command boosts to high, and
    the remaining-timer sensor uses it as the countdown length.
    """

    api: Nrf905Api
    coordinator: Nrf905Coordinator
    timer_minutes: int


Nrf905ConfigEntry = ConfigEntry[Nrf905Runtime]
