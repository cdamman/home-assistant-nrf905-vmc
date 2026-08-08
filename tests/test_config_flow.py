"""Tests for the nRF905 VMC config flow (user, reconfigure, reauth, options)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nrf905_vmc.api import Nrf905ApiError, Nrf905AuthError
from custom_components.nrf905_vmc.const import (
    CONF_POWER_HIGH,
    CONF_POWER_LOW,
    CONF_POWER_MEDIUM,
    DEFAULT_POWER_BY_SPEED,
    DOMAIN,
    SPEED_HIGH,
    SPEED_LOW,
    SPEED_MEDIUM,
)

from .conftest import (
    HOST,
    PASSWORD,
    POWER_SENSOR_ENTITY_ID,
    USERNAME,
    setup_integration,
)

USER_INPUT = {
    CONF_HOST: HOST,
    CONF_USERNAME: USERNAME,
    CONF_PASSWORD: PASSWORD,
}


@pytest.fixture
def mock_flow_api(mock_api: AsyncMock) -> AsyncMock:
    """Patch the API client instantiated by the config flow."""
    with patch(
        "custom_components.nrf905_vmc.config_flow.Nrf905Api",
        return_value=mock_api,
    ):
        yield mock_api


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_flow_api: AsyncMock
) -> None:
    """A reachable device creates one entry keyed on its IP address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"VMC {HOST}"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == HOST


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (Nrf905AuthError("nope"), "invalid_auth"),
        (Nrf905ApiError("unreachable"), "cannot_connect"),
        (RuntimeError("kaboom"), "unknown"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant,
    mock_flow_api: AsyncMock,
    error: Exception,
    reason: str,
) -> None:
    """Validation failures show an error and the form stays usable."""
    working = mock_flow_api.async_get_status.side_effect
    mock_flow_api.async_get_status.side_effect = error

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}

    mock_flow_api.async_get_status.side_effect = working
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_aborts_on_duplicate_host(
    hass: HomeAssistant,
    mock_flow_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The same IP address cannot be configured twice."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_entry(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_flow_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reconfiguring stores the new host and credentials."""
    await setup_integration(hass, mock_config_entry)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_input = {
        CONF_HOST: "192.168.1.99",
        CONF_USERNAME: "other",
        CONF_PASSWORD: "secret",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], new_input
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data == new_input


async def test_reconfigure_keeps_form_on_error(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_flow_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An unreachable device leaves the existing configuration untouched."""
    await setup_integration(hass, mock_config_entry)
    original = dict(mock_config_entry.data)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    mock_flow_api.async_get_status.side_effect = Nrf905ApiError("unreachable")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**original, CONF_HOST: "10.0.0.1"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert mock_config_entry.data == original


async def test_reauth_updates_credentials(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_flow_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Reauth only asks for credentials and keeps the host."""
    await setup_integration(hass, mock_config_entry)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "admin", CONF_PASSWORD: "new-secret"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data == {
        CONF_HOST: HOST,
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "new-secret",
    }


async def test_reauth_invalid_credentials(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_flow_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Wrong credentials keep the reauth form open."""
    await setup_integration(hass, mock_config_entry)

    result = await mock_config_entry.start_reauth_flow(hass)
    mock_flow_api.async_get_status.side_effect = Nrf905AuthError("nope")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "admin", CONF_PASSWORD: "wrong"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data[CONF_PASSWORD] == PASSWORD


async def test_options_flow_stores_the_power_values(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The three power values are written to the entry options."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_POWER_LOW: 15, CONF_POWER_MEDIUM: 30, CONF_POWER_HIGH: 62.5},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {
        CONF_POWER_LOW: 15,
        CONF_POWER_MEDIUM: 30,
        CONF_POWER_HIGH: 62.5,
    }


async def test_options_flow_suggests_the_current_values(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The form opens on the values already in use, defaults included."""
    await setup_integration(hass, mock_config_entry, options={CONF_POWER_HIGH: 62.5})

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
    }
    assert suggested == {
        CONF_POWER_LOW: DEFAULT_POWER_BY_SPEED[SPEED_LOW],
        CONF_POWER_MEDIUM: DEFAULT_POWER_BY_SPEED[SPEED_MEDIUM],
        CONF_POWER_HIGH: 62.5,
    }


async def test_options_flow_reloads_the_entry(
    hass: HomeAssistant,
    mock_api: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_status: dict[str, Any],
) -> None:
    """Saving new options takes effect without a restart."""
    device_status["speed"] = SPEED_HIGH
    await setup_integration(hass, mock_config_entry)
    assert float(hass.states.get(POWER_SENSOR_ENTITY_ID).state) == 58.5

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_POWER_LOW: 13, CONF_POWER_MEDIUM: 28, CONF_POWER_HIGH: 62.5},
    )
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert float(hass.states.get(POWER_SENSOR_ENTITY_ID).state) == 62.5
