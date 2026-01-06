"""Helpers shared by the entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER, MODEL
from .models import Nrf905ConfigEntry


def build_device_info(entry: Nrf905ConfigEntry) -> DeviceInfo:
    """Return the device info that groups every entity of one entry (= one IP)."""
    host = entry.data[CONF_HOST]
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"VMC {host}",
        manufacturer=MANUFACTURER,
        model=MODEL,
        configuration_url=f"http://{host}",
    )
