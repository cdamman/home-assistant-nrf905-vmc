"""Fan (ventilation) platform for nRF905 VMC."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    PRESET_MODES,
    PRESET_TO_SPEED,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
    SPEED_TO_PRESET,
)
from .coordinator import Nrf905Coordinator
from .entity import build_device_info
from .models import Nrf905ConfigEntry

_LOGGER = logging.getLogger(__name__)

# The nRF905 bridge applies a speed change with some latency, so an immediate
# status poll would still report the previous speed. After sending a command we
# show the requested speed optimistically and poll again a few seconds later
# (this also lets the remaining-timer sensor pick up the device's timer flag).
REFRESH_DELAY = 3  # seconds before the confirmation poll
OPTIMISTIC_TIMEOUT = 45  # seconds after which the optimistic value is dropped

# Map whatever the firmware reports to our canonical speed names.
# The exact key/format of querydevice.json is device-specific, so we try a
# handful of common keys and value spellings. Adjust here if your device
# reports the speed differently (see README).
SPEED_ALIASES: dict[str, str] = {
    "low": SPEED_LOW,
    "medium": SPEED_MEDIUM,
    "high": SPEED_HIGH,
    "min": SPEED_LOW,
    "mid": SPEED_MEDIUM,
    "max": SPEED_HIGH,
    "1": SPEED_LOW,
    "2": SPEED_MEDIUM,
    "3": SPEED_HIGH,
}
SPEED_KEYS = ("speed", "level", "state", "mode", "fan_speed", "fanspeed")


def _parse_speed(device: dict[str, Any]) -> str | None:
    for key in SPEED_KEYS:
        if key in device:
            value = str(device[key]).strip().lower()
            if value in SPEED_ALIASES:
                return SPEED_ALIASES[value]
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Nrf905ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ventilation fan entity."""
    async_add_entities([Nrf905Fan(entry)])


class Nrf905Fan(CoordinatorEntity[Nrf905Coordinator], FanEntity):
    """Ventilation modeled as a fan with three preset modes (Bas/Normal/Fort).

    Preset labels are kept in French so Google Home shows them in French (its
    integration forwards the raw preset strings, ignoring HA translations).
    On top of the three speeds, the on/off commands act as a "boost" control:
    turning on switches to high (with the auto-revert timer), turning off
    switches to medium.
    """

    _attr_has_entity_name = True
    _attr_name = None  # main feature -> uses the device name
    _attr_icon = "mdi:hvac"
    _attr_preset_modes = PRESET_MODES
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, entry: Nrf905ConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._runtime = entry.runtime_data
        self._api = entry.runtime_data.api
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = build_device_info(entry)
        self._optimistic_speed: str | None = None
        self._optimistic_until: float = 0.0

    @property
    def _current_speed(self) -> str | None:
        # Prefer the optimistic value briefly after a command, so Google Home
        # doesn't flicker while the bridge is still applying the change.
        if self._optimistic_speed is not None:
            if self.hass.loop.time() < self._optimistic_until:
                return self._optimistic_speed
            self._optimistic_speed = None
        return _parse_speed(self.coordinator.data or {})

    @callback
    def _handle_coordinator_update(self) -> None:
        # Drop the optimistic value once the device confirms the new speed.
        if self._optimistic_speed is not None and (
            _parse_speed(self.coordinator.data or {}) == self._optimistic_speed
        ):
            self._optimistic_speed = None
        super()._handle_coordinator_update()

    @property
    def preset_mode(self) -> str | None:
        speed = self._current_speed
        return SPEED_TO_PRESET.get(speed) if speed is not None else None

    @property
    def is_on(self) -> bool | None:
        # On/off is a boost representation on top of the 3 speeds:
        #   on  -> high (+ auto-revert timer),  off -> medium.
        # So the entity reads as "on" only while running at high speed.
        speed = self._current_speed
        if speed is None:
            return None
        return speed == SPEED_HIGH

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {"timer_minutes": self._runtime.timer_minutes}
        if "timer" in data:
            attrs["timer_active"] = bool(data["timer"])
        return attrs

    async def _async_apply(self, speed: str, timer: int | None = None) -> None:
        # Reflect the request immediately (before the slow bridge call) so HA and
        # Google see the new state right away, then confirm with a delayed poll.
        self._optimistic_speed = speed
        self._optimistic_until = self.hass.loop.time() + OPTIMISTIC_TIMEOUT
        self.async_write_ha_state()
        try:
            await self._api.async_set_speed(speed, timer)
        except Exception:
            self._optimistic_speed = None
            self.async_write_ha_state()
            raise
        async_call_later(self.hass, REFRESH_DELAY, self._async_delayed_refresh)

    async def _async_delayed_refresh(self, _now: Any) -> None:
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the ventilation speed. Selecting a preset never adds a timer."""
        if preset_mode not in PRESET_TO_SPEED:
            raise ValueError(f"Unsupported preset: {preset_mode}")
        await self._async_apply(PRESET_TO_SPEED[preset_mode])

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on -> high, always with the auto-revert timer.

        The timer is forced on the "on" command using the configurable delay.
        If a specific preset_mode is requested instead (e.g. from the speed
        selector), it is set without a timer.
        """
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
        else:
            await self._async_apply(SPEED_HIGH, self._runtime.timer_minutes)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off -> medium (baseline ventilation)."""
        await self._async_apply(SPEED_MEDIUM)
