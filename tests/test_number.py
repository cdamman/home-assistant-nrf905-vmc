"""Tests for the timer-duration number entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.components.number import (
    ATTR_MAX,
    ATTR_MIN,
    ATTR_STEP,
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.nrf905_vmc.const import (
    DEFAULT_TIMER_MINUTES,
    MAX_TIMER_MINUTES,
    MIN_TIMER_MINUTES,
)

from .conftest import NUMBER_ENTITY_ID, setup_integration


async def test_default_value_and_bounds(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """The entity starts at the default duration and exposes its bounds."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(NUMBER_ENTITY_ID)
    assert state.state == str(DEFAULT_TIMER_MINUTES)
    assert state.attributes[ATTR_MIN] == MIN_TIMER_MINUTES
    assert state.attributes[ATTR_MAX] == MAX_TIMER_MINUTES
    assert state.attributes[ATTR_STEP] == 1
    assert state.attributes["unit_of_measurement"] == UnitOfTime.MINUTES

    entry = entity_registry.async_get(NUMBER_ENTITY_ID)
    assert entry.entity_category is EntityCategory.CONFIG
    assert entry.unique_id == f"{mock_config_entry.entry_id}_timer_duration"


async def test_set_value_updates_shared_runtime(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Changing the number updates the value the fan uses as its boost delay."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: NUMBER_ENTITY_ID, ATTR_VALUE: 45},
        blocking=True,
    )

    assert hass.states.get(NUMBER_ENTITY_ID).state == "45"
    assert mock_config_entry.runtime_data.timer_minutes == 45


async def test_set_value_truncates_to_whole_minutes(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The delay is stored as whole minutes."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: NUMBER_ENTITY_ID, ATTR_VALUE: 12.7},
        blocking=True,
    )

    assert mock_config_entry.runtime_data.timer_minutes == 12


@pytest.mark.parametrize("value", [MIN_TIMER_MINUTES - 1, MAX_TIMER_MINUTES + 1])
async def test_out_of_range_values_are_rejected(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    value: int,
) -> None:
    """Values outside 1-240 minutes are refused."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: NUMBER_ENTITY_ID, ATTR_VALUE: value},
            blocking=True,
        )

    assert mock_config_entry.runtime_data.timer_minutes == DEFAULT_TIMER_MINUTES


async def test_value_is_restored_after_restart(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The configured duration survives a Home Assistant restart."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(NUMBER_ENTITY_ID, "60"),
                {
                    "native_max_value": MAX_TIMER_MINUTES,
                    "native_min_value": MIN_TIMER_MINUTES,
                    "native_step": 1,
                    "native_unit_of_measurement": UnitOfTime.MINUTES,
                    "native_value": 60.0,
                },
            ),
        ),
    )

    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(NUMBER_ENTITY_ID).state == "60"
    assert mock_config_entry.runtime_data.timer_minutes == 60
