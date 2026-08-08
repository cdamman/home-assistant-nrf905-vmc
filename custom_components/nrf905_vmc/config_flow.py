"""Config flow for nRF905 VMC (setup, reconfigure, reauth and options)."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import voluptuous as vol

from .api import Nrf905Api, Nrf905ApiError, Nrf905AuthError
from .const import (
    DEFAULT_POWER_BY_SPEED,
    DOMAIN,
    MAX_POWER_WATTS,
    MIN_POWER_WATTS,
    POWER_OPTION_BY_SPEED,
)
from .models import power_by_speed

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

# One watt field per speed. The device does not report its consumption, so the
# sensors derive it from these values; they default to the unit this
# integration was written against.
STEP_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(key, default=DEFAULT_POWER_BY_SPEED[speed]): NumberSelector(
            NumberSelectorConfig(
                min=MIN_POWER_WATTS,
                max=MAX_POWER_WATTS,
                step=0.1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfPower.WATT,
            )
        )
        for speed, key in POWER_OPTION_BY_SPEED.items()
    }
)


class Nrf905ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> Nrf905OptionsFlow:
        """Return the options flow handler (per-speed power draw)."""
        return Nrf905OptionsFlow()

    async def _validate(self, data: Mapping[str, Any]) -> dict[str, str]:
        """Try to reach the device; return an errors dict (empty on success)."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)
        api = Nrf905Api(
            session, data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD]
        )
        try:
            await api.async_get_status()
        except Nrf905AuthError:
            errors["base"] = "invalid_auth"
        except Nrf905ApiError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating nRF905 VMC")
            errors["base"] = "unknown"
        return errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()
            errors = await self._validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title=f"VMC {user_input[CONF_HOST]}", data=user_input
                )
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change IP address and/or credentials of an existing device."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate(user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for fresh credentials when authentication fails."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            merged = {**entry.data, **user_input}
            errors = await self._validate(merged)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_REAUTH_SCHEMA, {CONF_USERNAME: entry.data.get(CONF_USERNAME)}
            ),
            errors=errors,
        )


class Nrf905OptionsFlow(OptionsFlow):
    """Let the user enter the power draw of each ventilation speed."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show (and store) one power value per speed, in watts."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                STEP_OPTIONS_SCHEMA,
                {
                    POWER_OPTION_BY_SPEED[speed]: watts
                    for speed, watts in power_by_speed(
                        self.config_entry.options
                    ).items()
                },
            ),
        )
