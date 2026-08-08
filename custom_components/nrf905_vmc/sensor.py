"""Sensor platform: remaining auto-revert timer.

The device only tells us *whether* a timer is running (the boolean ``timer``
field of querydevice.json), not how long is left. So we start a countdown when
that flag turns true, using the configured timer length as the duration, and
clear it when the flag turns false. This device flag is the single source of
truth for the sensor.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import POWER_BY_SPEED
from .coordinator import Nrf905Coordinator
from .entity import build_device_info
from .fan import _parse_speed
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
    """Set up the sensors (remaining timer, power, daily energy)."""
    async_add_entities(
        [
            Nrf905TimerRemaining(entry),
            Nrf905Power(entry),
            Nrf905EnergyToday(entry),
        ]
    )


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
        return max(0, math.ceil(remaining / 60))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"finishes_at": self._end.isoformat() if self._end else None}


class Nrf905Power(CoordinatorEntity[Nrf905Coordinator], SensorEntity):
    """Instantaneous electrical power, derived from the current speed."""

    _attr_has_entity_name = True
    _attr_translation_key = "power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, entry: Nrf905ConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_device_info = build_device_info(entry)

    @property
    def native_value(self) -> float | None:
        speed = _parse_speed(self.coordinator.data or {})
        if speed is None:
            return None
        return POWER_BY_SPEED.get(speed)


class Nrf905EnergyToday(CoordinatorEntity[Nrf905Coordinator], RestoreSensor):
    """Energy consumed since local midnight, integrated from the power draw.

    The value is a Riemann sum of ``power * elapsed_time`` (updated on every
    speed change and on a periodic tick), reset to zero at local midnight and
    restored across restarts.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "energy_today"
    _attr_icon = "mdi:lightning-bolt"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(self, entry: Nrf905ConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_energy_today"
        self._attr_device_info = build_device_info(entry)
        self._energy_wh: float = 0.0
        self._power: float = 0.0
        self._last_ts: datetime | None = None
        self._day: date | None = None

    def _current_power(self) -> float:
        speed = _parse_speed(self.coordinator.data or {})
        return POWER_BY_SPEED.get(speed, 0.0) if speed is not None else 0.0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        today = dt_util.now().date()
        restored_day: date | None = None
        last_state = await self.async_get_last_state()
        if last_state is not None:
            day_str = last_state.attributes.get("date")
            if day_str:
                try:
                    restored_day = date.fromisoformat(day_str)
                except ValueError:
                    restored_day = None

        last_data = await self.async_get_last_sensor_data()
        if (
            last_data is not None
            and last_data.native_value is not None
            and restored_day == today
        ):
            # Continue today's accumulation.
            self._energy_wh = float(last_data.native_value) * 1000.0
        else:
            self._energy_wh = 0.0
        self._day = today
        self._power = self._current_power()
        # Don't count downtime as consumption: start integrating from now.
        self._last_ts = dt_util.utcnow()

        self.async_on_remove(
            async_track_time_interval(self.hass, self._async_tick, TICK_INTERVAL)
        )
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._async_midnight, hour=0, minute=0, second=0
            )
        )

    def _accumulate(self, now: datetime) -> None:
        if self._last_ts is not None:
            elapsed_h = (now - self._last_ts).total_seconds() / 3600.0
            if elapsed_h > 0:
                self._energy_wh += self._power * elapsed_h
        self._last_ts = now

    @callback
    def _handle_coordinator_update(self) -> None:
        # Close the interval with the previous power, then adopt the new one.
        self._accumulate(dt_util.utcnow())
        self._power = self._current_power()
        super()._handle_coordinator_update()

    @callback
    def _async_tick(self, _now: Any) -> None:
        self._accumulate(dt_util.utcnow())
        self.async_write_ha_state()

    @callback
    def _async_midnight(self, _now: Any) -> None:
        # Bank the tail of the previous day, then start the new day at zero.
        self._accumulate(dt_util.utcnow())
        self._energy_wh = 0.0
        self._day = dt_util.now().date()
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._energy_wh / 1000.0, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"date": (self._day or dt_util.now().date()).isoformat()}
