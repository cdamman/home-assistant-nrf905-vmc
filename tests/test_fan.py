"""Tests for the ventilation fan entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, call

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.fan import (
    ATTR_PRESET_MODE,
    ATTR_PRESET_MODES,
    DOMAIN as FAN_DOMAIN,
    SERVICE_SET_PRESET_MODE,
    FanEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_component import DATA_INSTANCES
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.nrf905_vmc.api import Nrf905ConnectionError
from custom_components.nrf905_vmc.const import (
    DEFAULT_TIMER_MINUTES,
    PRESET_HIGH,
    PRESET_LOW,
    PRESET_MEDIUM,
    PRESET_MODES,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
)
from custom_components.nrf905_vmc.fan import (
    OPTIMISTIC_TIMEOUT,
    REFRESH_DELAY,
    _parse_speed,
)

from .conftest import FAN_ENTITY_ID, setup_integration


@pytest.mark.parametrize(
    ("device", "expected"),
    [
        ({"speed": "low"}, SPEED_LOW),
        ({"speed": "MEDIUM"}, SPEED_MEDIUM),
        ({"speed": " High "}, SPEED_HIGH),
        ({"speed": "min"}, SPEED_LOW),
        ({"speed": "mid"}, SPEED_MEDIUM),
        ({"speed": "max"}, SPEED_HIGH),
        ({"speed": 1}, SPEED_LOW),
        ({"speed": 2}, SPEED_MEDIUM),
        ({"speed": 3}, SPEED_HIGH),
        ({"level": "high"}, SPEED_HIGH),
        ({"state": "low"}, SPEED_LOW),
        ({"mode": "medium"}, SPEED_MEDIUM),
        ({"fan_speed": "high"}, SPEED_HIGH),
        ({"fanspeed": "low"}, SPEED_LOW),
        ({"speed": "turbo"}, None),
        ({"speed": 4}, None),
        ({"unrelated": "low"}, None),
        ({}, None),
    ],
)
def test_parse_speed(device: dict[str, Any], expected: str | None) -> None:
    """Firmware speed spellings are normalised to our canonical names."""
    assert _parse_speed(device) == expected


async def test_fan_state_and_attributes(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The fan advertises the three French presets and the timer attributes."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(FAN_ENTITY_ID)
    assert state.state == STATE_OFF  # low speed -> not boosting
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_LOW
    assert state.attributes[ATTR_PRESET_MODES] == PRESET_MODES
    assert state.attributes["timer_minutes"] == DEFAULT_TIMER_MINUTES
    assert state.attributes["timer_active"] is False
    assert state.attributes[ATTR_SUPPORTED_FEATURES] == (
        FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )


@pytest.mark.parametrize(
    ("speed", "expected_state", "expected_preset"),
    [
        (SPEED_LOW, STATE_OFF, PRESET_LOW),
        (SPEED_MEDIUM, STATE_OFF, PRESET_MEDIUM),
        (SPEED_HIGH, STATE_ON, PRESET_HIGH),
    ],
)
async def test_fan_reflects_device_speed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    speed: str,
    expected_state: str,
    expected_preset: str,
) -> None:
    """On/off is a boost representation: only "high" reads as on."""
    device_status["speed"] = speed
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(FAN_ENTITY_ID)
    assert state.state == expected_state
    assert state.attributes[ATTR_PRESET_MODE] == expected_preset


async def test_fan_state_unknown_when_speed_unparseable(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """An unrecognised speed leaves the entity in the unknown state."""
    device_status.clear()
    device_status["speed"] = "turbo"
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(FAN_ENTITY_ID)
    assert state.state == STATE_UNKNOWN
    assert state.attributes[ATTR_PRESET_MODE] is None
    assert "timer_active" not in state.attributes


@pytest.mark.parametrize(
    ("preset", "expected_speed"),
    [
        (PRESET_LOW, SPEED_LOW),
        (PRESET_MEDIUM, SPEED_MEDIUM),
        (PRESET_HIGH, SPEED_HIGH),
    ],
)
async def test_set_preset_mode_never_sets_a_timer(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    preset: str,
    expected_speed: str,
) -> None:
    """Selecting a speed from the preset list is a plain speed change."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: FAN_ENTITY_ID, ATTR_PRESET_MODE: preset},
        blocking=True,
    )

    assert mock_api.async_set_speed.mock_calls == [call(expected_speed, None)]


async def test_set_unknown_preset_is_rejected(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Home Assistant rejects presets outside the advertised list."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: FAN_ENTITY_ID, ATTR_PRESET_MODE: "4 - Turbo"},
            blocking=True,
        )

    mock_api.async_set_speed.assert_not_called()


async def test_entity_guards_against_unknown_preset(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The entity itself also refuses a preset it cannot map to a speed."""
    await setup_integration(hass, mock_config_entry)
    entity = hass.data[DATA_INSTANCES][FAN_DOMAIN].get_entity(FAN_ENTITY_ID)

    with pytest.raises(ValueError):
        await entity.async_set_preset_mode("4 - Turbo")

    mock_api.async_set_speed.assert_not_called()


async def test_turn_on_boosts_to_high_with_timer(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Turning on switches to high speed with the auto-revert delay."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN_ENTITY_ID},
        blocking=True,
    )

    assert mock_api.async_set_speed.mock_calls == [
        call(SPEED_HIGH, DEFAULT_TIMER_MINUTES)
    ]


async def test_turn_on_with_preset_has_no_timer(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """An explicit preset on turn_on bypasses the boost timer."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN_ENTITY_ID, ATTR_PRESET_MODE: PRESET_MEDIUM},
        blocking=True,
    )

    assert mock_api.async_set_speed.mock_calls == [call(SPEED_MEDIUM, None)]


async def test_turn_off_falls_back_to_medium(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """Turning off returns to the baseline (medium) ventilation."""
    device_status["speed"] = SPEED_HIGH
    await setup_integration(hass, mock_config_entry)
    assert hass.states.get(FAN_ENTITY_ID).state == STATE_ON

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: FAN_ENTITY_ID},
        blocking=True,
    )

    assert mock_api.async_set_speed.mock_calls == [call(SPEED_MEDIUM, None)]


async def test_optimistic_state_before_device_confirms(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The requested speed shows immediately, even before the device catches up."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN_ENTITY_ID},
        blocking=True,
    )

    # The device still reports the old speed, but the entity does not flicker.
    assert hass.states.get(FAN_ENTITY_ID).state == STATE_ON
    assert hass.states.get(FAN_ENTITY_ID).attributes[ATTR_PRESET_MODE] == PRESET_HIGH

    # A confirmation poll is scheduled shortly after the command.
    mock_api.async_get_status.reset_mock()
    freezer.tick(REFRESH_DELAY + 1)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_api.async_get_status.called

    # Once the device confirms, the optimistic value is dropped.
    device_status["speed"] = SPEED_HIGH
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(FAN_ENTITY_ID).state == STATE_ON


async def test_optimistic_state_expires(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A device that never applies the command wins back after the timeout."""
    await setup_integration(hass, mock_config_entry)

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN_ENTITY_ID},
        blocking=True,
    )
    assert hass.states.get(FAN_ENTITY_ID).state == STATE_ON

    freezer.tick(OPTIMISTIC_TIMEOUT + 1)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # Back to what the device actually reports (low -> off).
    assert hass.states.get(FAN_ENTITY_ID).state == STATE_OFF
    assert hass.states.get(FAN_ENTITY_ID).attributes[ATTR_PRESET_MODE] == PRESET_LOW


async def test_failed_command_reverts_optimistic_state(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A rejected command does not leave a stale optimistic state behind."""
    await setup_integration(hass, mock_config_entry)
    mock_api.async_set_speed.side_effect = Nrf905ConnectionError("unreachable")

    with pytest.raises(Nrf905ConnectionError):
        await hass.services.async_call(
            FAN_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: FAN_ENTITY_ID},
            blocking=True,
        )

    assert hass.states.get(FAN_ENTITY_ID).state == STATE_OFF
    assert hass.states.get(FAN_ENTITY_ID).attributes[ATTR_PRESET_MODE] == PRESET_LOW


async def test_timer_attributes_follow_the_number_entity(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """The boost uses whatever duration the number entity currently holds."""
    await setup_integration(hass, mock_config_entry)
    mock_config_entry.runtime_data.timer_minutes = 90
    device_status["timer"] = True
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(FAN_ENTITY_ID)
    assert state.attributes["timer_minutes"] == 90
    assert state.attributes["timer_active"] is True

    await hass.services.async_call(
        FAN_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: FAN_ENTITY_ID},
        blocking=True,
    )

    assert mock_api.async_set_speed.mock_calls == [call(SPEED_HIGH, 90)]
