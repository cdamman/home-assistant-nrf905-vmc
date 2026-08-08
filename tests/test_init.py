"""Tests for the integration setup/unload and the update coordinator."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nrf905_vmc.api import Nrf905ApiError, Nrf905AuthError
from custom_components.nrf905_vmc.const import (
    DEFAULT_TIMER_MINUTES,
    DOMAIN,
    MANUFACTURER,
    MAX_UPDATE_FAILURES,
    MODEL,
    SCAN_INTERVAL,
)

from .conftest import (
    ENERGY_SENSOR_ENTITY_ID,
    FAN_ENTITY_ID,
    HOST,
    NUMBER_ENTITY_ID,
    POWER_SENSOR_ENTITY_ID,
    TIMER_SENSOR_ENTITY_ID,
    setup_integration,
)


async def test_setup_and_unload(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The entry loads, exposes its runtime data and unloads cleanly."""
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data.timer_minutes == DEFAULT_TIMER_MINUTES
    assert mock_config_entry.runtime_data.coordinator.data == {
        "speed": "low",
        "timer": False,
    }

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_device_unreachable(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """An unreachable device puts the entry in the retry state."""
    mock_api.async_get_status.side_effect = Nrf905ApiError("unreachable")
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_starts_reauth_on_auth_error(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Rejected credentials trigger the reauth flow."""
    mock_api.async_get_status.side_effect = Nrf905AuthError("nope")
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_device_registry_entry(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Every entity of one config entry is grouped under a single device."""
    await setup_integration(hass, mock_config_entry)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, mock_config_entry.entry_id)}
    )
    assert device is not None
    assert device.name == f"VMC {HOST}"
    assert device.manufacturer == MANUFACTURER
    assert device.model == MODEL
    assert device.configuration_url == f"http://{HOST}"


async def test_transient_errors_keep_last_state(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A few failed polls in a row keep the last known state."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator

    mock_api.async_get_status.side_effect = Nrf905ApiError("hiccup")
    for _ in range(MAX_UPDATE_FAILURES - 1):
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

        assert coordinator.last_update_success
        assert coordinator.data == {"speed": "low", "timer": False}
        assert hass.states.get(FAN_ENTITY_ID).state == "off"

    # One more failure crosses the tolerance threshold.
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    assert hass.states.get(FAN_ENTITY_ID).state == "unavailable"


async def test_failure_counter_resets_after_recovery(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A successful poll clears the tolerated-failure counter."""
    await setup_integration(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    working = mock_api.async_get_status.side_effect

    for _ in range(MAX_UPDATE_FAILURES * 2):
        mock_api.async_get_status.side_effect = Nrf905ApiError("hiccup")
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert coordinator.last_update_success

        mock_api.async_get_status.side_effect = working
        freezer.tick(SCAN_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert coordinator.last_update_success


async def test_auth_error_while_polling_triggers_reauth(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Credentials rejected mid-flight start a reauth flow immediately."""
    await setup_integration(hass, mock_config_entry)

    mock_api.async_get_status.side_effect = Nrf905AuthError("expired")
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


@pytest.mark.parametrize(
    "entity_id",
    [
        FAN_ENTITY_ID,
        NUMBER_ENTITY_ID,
        TIMER_SENSOR_ENTITY_ID,
        POWER_SENSOR_ENTITY_ID,
        ENERGY_SENSOR_ENTITY_ID,
    ],
)
async def test_platforms_are_set_up(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_id: str,
) -> None:
    """Every advertised entity exists once the entry is loaded."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(entity_id) is not None
