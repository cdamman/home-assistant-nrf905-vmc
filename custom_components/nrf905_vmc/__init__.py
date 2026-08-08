"""The nRF905 VMC integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import Nrf905Api
from .const import DEFAULT_TIMER_MINUTES
from .coordinator import Nrf905Coordinator
from .models import Nrf905ConfigEntry, Nrf905Runtime, power_by_speed

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.FAN, Platform.NUMBER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: Nrf905ConfigEntry) -> bool:
    """Set up nRF905 VMC from a config entry."""
    session = async_get_clientsession(hass)
    api = Nrf905Api(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    coordinator = Nrf905Coordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = Nrf905Runtime(
        api=api,
        coordinator=coordinator,
        timer_minutes=DEFAULT_TIMER_MINUTES,
        power_by_speed=power_by_speed(entry.options),
    )

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: Nrf905ConfigEntry) -> None:
    """Reload the entry so the new power values reach the sensors."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: Nrf905ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
