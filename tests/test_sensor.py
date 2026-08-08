"""Tests for the timer-remaining, power and daily-energy sensors."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNKNOWN,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from custom_components.nrf905_vmc.const import (
    CONF_POWER_HIGH,
    CONF_POWER_LOW,
    CONF_POWER_MEDIUM,
    DEFAULT_POWER_BY_SPEED,
    SCAN_INTERVAL,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
)
from custom_components.nrf905_vmc.sensor import TICK_INTERVAL, _timer_active

from .conftest import (
    ENERGY_SENSOR_ENTITY_ID,
    POWER_SENSOR_ENTITY_ID,
    TIMER_SENSOR_ENTITY_ID,
    setup_integration,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (2.5, True),
        (0.0, False),
        ("true", True),
        ("True", True),
        (" on ", True),
        ("YES", True),
        ("1", True),
        ("false", False),
        ("off", False),
        ("", False),
        (None, False),
        ([], False),
    ],
)
def test_timer_active(value: Any, expected: bool) -> None:
    """The device timer flag is read from several possible spellings."""
    assert _timer_active({"timer": value}) is expected


def test_timer_active_without_key() -> None:
    """A payload without a timer field means no timer."""
    assert _timer_active({}) is False


# --------------------------------------------------------------------------
# Timer remaining
# --------------------------------------------------------------------------


async def test_timer_remaining_unknown_when_idle(
    hass: HomeAssistant, mock_api: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """No countdown is shown while the device reports no timer."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(TIMER_SENSOR_ENTITY_ID)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["finishes_at"] is None
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.DURATION
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTime.MINUTES


async def test_timer_remaining_counts_down(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The countdown starts on the rising edge of the device timer flag."""
    await setup_integration(hass, mock_config_entry)
    mock_config_entry.runtime_data.timer_minutes = 30

    device_status["timer"] = True
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(TIMER_SENSOR_ENTITY_ID).state == "30"

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(TIMER_SENSOR_ENTITY_ID).state == "20"


async def test_timer_remaining_never_negative(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """An overdue countdown floors at zero instead of going negative."""
    await setup_integration(hass, mock_config_entry)
    mock_config_entry.runtime_data.timer_minutes = 5

    device_status["timer"] = True
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(TIMER_SENSOR_ENTITY_ID).state == "0"


async def test_timer_remaining_window_is_not_restarted(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A timer that stays on keeps its original end time across polls."""
    await setup_integration(hass, mock_config_entry)
    mock_config_entry.runtime_data.timer_minutes = 30

    device_status["timer"] = True
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    finishes_at = hass.states.get(TIMER_SENSOR_ENTITY_ID).attributes["finishes_at"]

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        hass.states.get(TIMER_SENSOR_ENTITY_ID).attributes["finishes_at"] == finishes_at
    )


async def test_timer_remaining_cleared_when_flag_drops(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """The countdown is cleared as soon as the device reports no timer."""
    await setup_integration(hass, mock_config_entry)

    device_status["timer"] = True
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(TIMER_SENSOR_ENTITY_ID).state != STATE_UNKNOWN

    device_status["timer"] = False
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(TIMER_SENSOR_ENTITY_ID).state == STATE_UNKNOWN


async def test_timer_remaining_initialised_from_first_poll(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """A timer already running at startup is picked up right away."""
    device_status["timer"] = True
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(TIMER_SENSOR_ENTITY_ID).state == "30"


# --------------------------------------------------------------------------
# Power
# --------------------------------------------------------------------------


@pytest.mark.parametrize("speed", [SPEED_LOW, SPEED_MEDIUM, SPEED_HIGH])
async def test_power_matches_speed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    speed: str,
) -> None:
    """Each speed maps to its documented power draw."""
    device_status["speed"] = speed
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(POWER_SENSOR_ENTITY_ID)
    assert float(state.state) == DEFAULT_POWER_BY_SPEED[speed]
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.POWER
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.WATT


async def test_power_unknown_for_unparseable_speed(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """An unrecognised speed yields no power reading."""
    device_status["speed"] = "turbo"
    await setup_integration(hass, mock_config_entry)

    assert hass.states.get(POWER_SENSOR_ENTITY_ID).state == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("speed", "option", "expected"),
    [
        (SPEED_LOW, CONF_POWER_LOW, 9.0),
        (SPEED_MEDIUM, CONF_POWER_MEDIUM, 21.5),
        (SPEED_HIGH, CONF_POWER_HIGH, 75.0),
    ],
)
async def test_power_uses_the_configured_values(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    speed: str,
    option: str,
    expected: float,
) -> None:
    """A unit with a different power draw reports its own values."""
    device_status["speed"] = speed
    await setup_integration(hass, mock_config_entry, options={option: expected})

    assert float(hass.states.get(POWER_SENSOR_ENTITY_ID).state) == expected


async def test_power_keeps_defaults_for_unconfigured_speeds(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """Configuring one speed leaves the others on their default."""
    device_status["speed"] = SPEED_MEDIUM
    await setup_integration(hass, mock_config_entry, options={CONF_POWER_HIGH: 75.0})

    assert (
        float(hass.states.get(POWER_SENSOR_ENTITY_ID).state)
        == DEFAULT_POWER_BY_SPEED[SPEED_MEDIUM]
    )


async def test_power_follows_speed_changes(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """The power reading tracks the device speed."""
    await setup_integration(hass, mock_config_entry)
    assert float(hass.states.get(POWER_SENSOR_ENTITY_ID).state) == 13.0

    device_status["speed"] = SPEED_HIGH
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert float(hass.states.get(POWER_SENSOR_ENTITY_ID).state) == 58.5


# --------------------------------------------------------------------------
# Daily energy
# --------------------------------------------------------------------------


async def test_energy_starts_at_zero(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Without restored data the daily counter starts empty."""
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(ENERGY_SENSOR_ENTITY_ID)
    assert float(state.state) == 0.0
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENERGY
    assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.TOTAL_INCREASING
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfEnergy.KILO_WATT_HOUR
    assert state.attributes["date"] == dt_util.now().date().isoformat()

    entry = entity_registry.async_get(ENERGY_SENSOR_ENTITY_ID)
    assert entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_energy_integrates_power_over_time(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Energy accumulates as power x elapsed time."""
    device_status["speed"] = SPEED_MEDIUM  # 28 W
    await setup_integration(hass, mock_config_entry)

    for _ in range(120):  # 120 x 30 s = 1 h
        freezer.tick(TICK_INTERVAL)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(
        0.028, abs=1e-3
    )


async def test_energy_integrates_the_configured_power(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The daily total is built from the configured power, not the default."""
    device_status["speed"] = SPEED_HIGH
    await setup_integration(hass, mock_config_entry, options={CONF_POWER_HIGH: 100.0})

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(
        0.1, abs=1e-3
    )


async def test_energy_survives_a_power_reconfiguration(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Changing the power keeps today's total and applies from that point on."""
    device_status["speed"] = SPEED_HIGH
    await setup_integration(hass, mock_config_entry, options={CONF_POWER_HIGH: 100.0})

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(
        0.1, abs=1e-3
    )

    # Halve the power; the entry reloads and integration resumes from the total.
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_POWER_HIGH: 50.0}
    )
    await hass.async_block_till_done()
    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(
        0.1, abs=1e-3
    )

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(
        0.15, abs=1e-3
    )


async def test_energy_uses_power_of_each_interval(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """A speed change closes the previous interval at the previous power."""
    device_status["speed"] = SPEED_LOW  # 13 W
    await setup_integration(hass, mock_config_entry)

    freezer.tick(timedelta(hours=1))
    device_status["speed"] = SPEED_HIGH  # 58.5 W
    await mock_config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    # 1 h at 13 W + 1 h at 58.5 W
    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(
        (13.0 + 58.5) / 1000.0, abs=1e-3
    )


async def test_energy_ignores_downtime(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """Integration restarts from "now", so downtime is not counted."""
    device_status["speed"] = SPEED_HIGH
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(
                    ENERGY_SENSOR_ENTITY_ID,
                    "1.5",
                    {"date": dt_util.now().date().isoformat()},
                ),
                {"native_value": 1.5, "native_unit_of_measurement": "kWh"},
            ),
        ),
    )

    await setup_integration(hass, mock_config_entry)

    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(1.5)


async def test_energy_restored_from_same_day(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Today's accumulation continues where the restart left off."""
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(
                    ENERGY_SENSOR_ENTITY_ID,
                    "0.100",
                    {"date": dt_util.now().date().isoformat()},
                ),
                {"native_value": 0.100, "native_unit_of_measurement": "kWh"},
            ),
        ),
    )
    device_status["speed"] = SPEED_MEDIUM  # 28 W

    await setup_integration(hass, mock_config_entry)
    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(0.1)

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == pytest.approx(
        0.128, abs=1e-3
    )


@pytest.mark.parametrize("stored_date", ["2020-01-01", "not-a-date", None])
async def test_energy_not_restored_from_another_day(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    stored_date: str | None,
) -> None:
    """Yesterday's total (or an unusable date) does not carry over."""
    attributes = {"date": stored_date} if stored_date is not None else {}
    mock_restore_cache_with_extra_data(
        hass,
        (
            (
                State(ENERGY_SENSOR_ENTITY_ID, "4.2", attributes),
                {"native_value": 4.2, "native_unit_of_measurement": "kWh"},
            ),
        ),
    )

    await setup_integration(hass, mock_config_entry)

    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) == 0.0


async def test_energy_resets_at_midnight(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The counter goes back to zero when the local day changes."""
    freezer.move_to(dt_util.now().replace(hour=23, minute=0, second=0, microsecond=0))
    device_status["speed"] = SPEED_HIGH
    await setup_integration(hass, mock_config_entry)

    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert float(hass.states.get(ENERGY_SENSOR_ENTITY_ID).state) > 0

    day_before = dt_util.now().date()
    freezer.tick(timedelta(minutes=31))  # crosses local midnight
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(ENERGY_SENSOR_ENTITY_ID)
    assert float(state.state) == pytest.approx(0.0, abs=1e-3)
    assert state.attributes["date"] != day_before.isoformat()
