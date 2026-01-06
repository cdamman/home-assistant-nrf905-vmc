"""Coordinator polling the device status."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Nrf905Api, Nrf905ApiError, Nrf905AuthError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class Nrf905Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch the current ventilation status on a schedule."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: Nrf905Api
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=entry,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_status()
        except Nrf905AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Nrf905ApiError as err:
            raise UpdateFailed(str(err)) from err
