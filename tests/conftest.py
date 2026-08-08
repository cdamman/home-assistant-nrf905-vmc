"""Shared fixtures for the nRF905 VMC tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nrf905_vmc.const import DOMAIN

HOST = "192.168.1.50"
USERNAME = "user"
PASSWORD = "pass"

# Entity ids are derived from the device name ("VMC <host>") and the English
# entity names declared in translations/en.json.
FAN_ENTITY_ID = "fan.vmc_192_168_1_50"
NUMBER_ENTITY_ID = "number.vmc_192_168_1_50_timer_duration"
TIMER_SENSOR_ENTITY_ID = "sensor.vmc_192_168_1_50_timer_remaining"
POWER_SENSOR_ENTITY_ID = "sensor.vmc_192_168_1_50_current_consumption"
ENERGY_SENSOR_ENTITY_ID = "sensor.vmc_192_168_1_50_today_s_consumption"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Load `custom_components/` in every test."""
    yield


@pytest.fixture
def device_status() -> dict[str, Any]:
    """Mutable device payload returned by the mocked API.

    Tests mutate this dict in place and request a coordinator refresh to
    simulate the device changing state.
    """
    return {"speed": "low", "timer": False}


@pytest.fixture
def mock_api(device_status: dict[str, Any]) -> Generator[MagicMock]:
    """Patch the API client used by the integration setup."""

    async def _get_status() -> dict[str, Any]:
        return dict(device_status)

    with patch("custom_components.nrf905_vmc.Nrf905Api", autospec=True) as api_class:
        api = api_class.return_value
        api.async_get_status = AsyncMock(side_effect=_get_status)
        api.async_set_speed = AsyncMock(return_value={"status": "ok"})
        yield api


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for one device."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"VMC {HOST}",
        unique_id=HOST,
        data={
            CONF_HOST: HOST,
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
        },
    )


async def setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry
) -> MockConfigEntry:
    """Add the entry to hass and set the integration up."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
