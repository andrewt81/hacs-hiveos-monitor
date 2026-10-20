"""Config flow for HiveOS Monitor."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HiveOSAPIError, HiveOSAuthError, HiveOSClient
from .const import CONF_API_TOKEN, CONF_FARM_ID, DOMAIN


class HiveOSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the HiveOS Monitor configuration flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            farm_id = str(user_input[CONF_FARM_ID]).strip()
            token = str(user_input[CONF_API_TOKEN]).strip()
            client = HiveOSClient(async_get_clientsession(self.hass), token, farm_id)
            try:
                await client.async_validate()
            except HiveOSAuthError:
                errors["base"] = "invalid_auth"
            except HiveOSAPIError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(farm_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"HiveOS farm {farm_id}",
                    data={CONF_API_TOKEN: token, CONF_FARM_ID: farm_id},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_TOKEN): str,
                vol.Required(CONF_FARM_ID): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
