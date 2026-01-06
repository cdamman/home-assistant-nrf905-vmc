"""Number platform: configurable timer duration (minutes)."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MAX_TIMER_MINUTES, MIN_TIMER_MINUTES
from .entity import build_device_info
from .models import Nrf905ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Nrf905ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the timer-duration number entity."""
    async_add_entities([Nrf905TimerDuration(entry)])


class Nrf905TimerDuration(RestoreNumber):
    """How long the auto-revert timer lasts when switching to high speed."""

    _attr_has_entity_name = True
    _attr_translation_key = "timer_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-cog-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_TIMER_MINUTES
    _attr_native_max_value = MAX_TIMER_MINUTES
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 0

    def __init__(self, entry: Nrf905ConfigEntry) -> None:
        self._runtime = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_timer_duration"
        self._attr_device_info = build_device_info(entry)
        self._attr_native_value = self._runtime.timer_minutes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = int(last.native_value)
            self._runtime.timer_minutes = int(last.native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = int(value)
        self._runtime.timer_minutes = int(value)
        self.async_write_ha_state()
