"""Sensor platform: remaining auto-revert timer.

The device only tells us *whether* a timer is running (the boolean ``timer``
field of querydevice.json), not how long is left. So we start a countdown when
that flag turns true, using the configured timer length as the duration, and
clear it when the flag turns false. This device flag is the single source of
truth for the sensor.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import Nrf905Coordinator
from .entity import build_device_info
from .models import Nrf905ConfigEntry

# The value depends on wall-clock time, so refresh it on its own cadence rather
# than only when the device is polled.
TICK_INTERVAL = timedelta(seconds=30)


def _timer_active(data: dict[str, Any]) -> bool:
    """Return whether the device reports a running timer."""
    value = data.get("timer")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "on", "yes")
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Nrf905ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the remaining-timer sensor."""
    async_add_entities([Nrf905TimerRemaining(entry)])


class Nrf905TimerRemaining(CoordinatorEntity[Nrf905Coordinator], SensorEntity):
    """Minutes left before the boost timer reverts the ventilation.

    Driven solely by the device's ``timer`` flag: the countdown starts when the
    flag rises and is cleared when it falls. The length is the configured timer
    duration. Unknown when no timer is running.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "timer_remaining"
    _attr_icon = "mdi:timer-sand"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, entry: Nrf905ConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_timer_remaining"
        self._attr_device_info = build_device_info(entry)
        self._end: datetime | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._sync_timer_window()  # initialise from current device data
        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_tick, TICK_INTERVAL)
        )

    @callback
    def _sync_timer_window(self) -> None:
        """Start/keep/clear the countdown window based on the device flag."""
        if _timer_active(self.coordinator.data or {}):
            if self._end is None:  # rising edge -> start the countdown
                self._end = dt_util.utcnow() + timedelta(
                    minutes=self._runtime.timer_minutes
                )
        else:
            self._end = None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync_timer_window()
        super()._handle_coordinator_update()

    @callback
    def _async_tick(self, _now: Any) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        if self._end is None:
            return None
        remaining = (self._end - dt_util.utcnow()).total_seconds()
        return max(0, int(math.ceil(remaining / 60)))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"finishes_at": self._end.isoformat() if self._end else None}

