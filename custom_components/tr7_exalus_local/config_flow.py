"""Config flow for the TR7 Exalus Local integration."""

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import DEFAULT_PORT, DOMAIN, CONF_SERIAL_NUMBER, CONF_PIN
from .tr7_api import TR7Client

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error raised when the TR7 unit is unreachable on the network."""


class InvalidAuth(HomeAssistantError):
    """Error raised when the serial number / PIN are rejected."""


async def validate_connection(
    hass: HomeAssistant, host: str, port: int, serial_number: str, pin: str
) -> dict[str, Any]:
    """Validate the connection to the TR7 system and return basic info."""
    email = "installator@installator"
    password = f"{serial_number.upper()}{pin}"

    client = TR7Client(host=host, port=port, email=email, password=password)

    try:
        if not await client.connect():
            # The socket opened but login failed -> bad serial/PIN.
            # The socket never opened -> host unreachable.
            if client.is_connected:
                raise InvalidAuth
            raise CannotConnect

        await asyncio.sleep(2)

        devices = await client.get_all_devices()

        return {
            "title": f"TR7 Exalus ({host})",
            "device_count": len(devices),
        }

    finally:
        await client.disconnect()


class TR7ExalusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for TR7 Exalus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a user-initiated configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_connection(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_SERIAL_NUMBER],
                    user_input[CONF_PIN],
                )

                # Use the serial number as the unique ID: it identifies the
                # device regardless of its (DHCP-volatile) IP address. If the
                # device is re-added on a new IP, refresh the stored host.
                await self.async_set_unique_id(
                    user_input[CONF_SERIAL_NUMBER].upper()
                )
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST]}
                )

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )

            except InvalidAuth:
                _LOGGER.warning("Authentication failed for TR7 at %s", user_input[CONF_HOST])
                errors["base"] = "invalid_auth"
            except CannotConnect:
                _LOGGER.error("Cannot connect to TR7 at %s", user_input[CONF_HOST])
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected validation error: %s", err)
                errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Required(CONF_SERIAL_NUMBER): str,
                vol.Required(CONF_PIN): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "example_host": "192.168.1.160",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow."""
        return TR7ExalusOptionsFlow(config_entry)


class TR7ExalusOptionsFlow(config_entries.OptionsFlow):
    """Options flow for TR7 Exalus."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
        )
