"""Config flow to configure Exta Life component."""

import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .helpers.const import (
    DOMAIN,
    CONF_CONTROLLER_IP,
    CONF_USER,
    CONF_PASSWORD,
    DEFAULT_POLL_INTERVAL,
    OPTIONS_LIGHT,
    OPTIONS_GENERAL,
    OPTIONS_COVER,
    OPTIONS_LIGHT_ICONS_LIST,
    OPTIONS_COVER_INVERTED_CONTROL,
    OPTIONS_GENERAL_POLL_INTERVAL,
    OPTIONS_GENERAL_DISABLE_NOT_RESPONDING
)
from .pyextalife import (
    ExtaLifeAPI,
    TCPConnError,
    DEVICE_ICON_ARR_LIGHT
)

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class ExtaLifeFlowHandler(config_entries.ConfigFlow):
    """ExtaLife config flow."""

    VERSION = 2
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize Exta Life configuration flow."""
        self._user_input = {}
        self._import_data = None
        self._controller_name = 'EFC-01'

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ExtaLifeOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            return await self.async_step_init(user_input=None)
        return self.async_show_form(step_id="confirm")

    async def async_step_confirm(self, user_input=None):
        """Handle flow start."""
        errors = {}
        if user_input is not None:
            return await self.async_step_init(user_input=None)
        return self.async_show_form(step_id="confirm", errors=errors)

    async def async_step_init(self, user_input=None):
        """Handle flow start.
        This step can be called either from GUI from step confirm or by step_import
        during entry migration"""

        errors = {}

        controller_ip = self._import_data.get(CONF_CONTROLLER_IP) if self._import_data else None
        description_placeholders = {"error_info": ""}
        if user_input is None or (self._import_data is not None and self._import_data.get(CONF_CONTROLLER_IP) is None):
            controller_ip = await self.hass.async_add_executor_job(ExtaLifeAPI.discover_controller)

        if user_input is not None or self._import_data is not None:
            try:
                if controller_ip is None:
                    controller_ip = user_input[CONF_CONTROLLER_IP]
                user = user_input[CONF_USER] if user_input else self._import_data[CONF_USER]
                password = user_input[CONF_PASSWORD] if user_input else self._import_data[CONF_PASSWORD]

                # Test connection on this IP - get instance: this will already try to connect and logon
                controller = ExtaLifeAPI(self.hass.loop)
                await controller.async_connect(user, password, host=controller_ip)
                self._controller_name = await controller.async_get_name()

                self._user_input = user_input

                # populate optional IP address if not provided in config already
                if self._import_data:
                    self._import_data[CONF_CONTROLLER_IP] = controller_ip

                # check if connection to this controller is already configured (based on MAC address)
                # for controllers accessed through internet this may lead to misidentification due to MAC
                # being MAC of a router, not a real EFC-01 MAC. For connections through VPN this should be ok
                await self.async_set_unique_id(controller.mac)

                await controller.disconnect()  # if we won't do this - it will run forever and ping

                self._abort_if_unique_id_configured()

                return await self.async_step_title()

            except TCPConnError as conn_error:
                if conn_error.error_code == -2:
                    _LOGGER.error("Invalid user or password. Correct and try again")
                    errors = {"base": "extalife_invalid_cred"}
                else:
                    _LOGGER.error(
                        "Cannot connect to your EFC-01 controller on IP %s with these credentials. "
                        "Check your user and password and try again. Error code: %s",
                        user_input[CONF_CONTROLLER_IP], conn_error.error_code
                    )
                    errors = {"base": "extalife_no_connection"}

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USER): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_CONTROLLER_IP, default=controller_ip): str
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_title(self, user_input=None):
        """Ask for additional title for Integrations screen. To differentiate in GUI between multiple config entries"""
        if user_input is not None or self._import_data is not None:
            title = user_input.get("title") if user_input else self._controller_name
            data = self._user_input if self._user_input else self._import_data
            return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="title",
            data_schema=vol.Schema(
                {vol.Optional("title", default=self._controller_name if self._controller_name else ''): str}
            ),
            errors={},
            description_placeholders={},
        )

    async def async_step_import(self, import_data):
        """ This step can only be called from component async_setup() and will migrate configuration.yaml entry
        into a Config Entry """
        self._import_data = import_data
        self._import_data.pop("options")     # options should not be part of config_entry.data

        # add default poll interval if not provided in config
        # self._import_data[CONF_POLL_INTERVAL] = self._import_data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

        # initiate the flow as from GUI, call step `init`
        return await self.async_step_init()


def get_default_options():

    options = {}
    options.setdefault(OPTIONS_GENERAL, {
        OPTIONS_GENERAL_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
        OPTIONS_GENERAL_DISABLE_NOT_RESPONDING: True
    })
    options.setdefault(OPTIONS_LIGHT, {
        OPTIONS_LIGHT_ICONS_LIST: DEVICE_ICON_ARR_LIGHT
    })
    options.setdefault(OPTIONS_COVER, {
        OPTIONS_COVER_INVERTED_CONTROL: False
    })
    return options.copy()


class ExtaLifeOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Exta Life options."""

    def __init__(self, config_entry):
        """Initialize Exta Life options flow."""
        self.options = config_entry.options.copy()

        if self.options == {}:
            self.options = get_default_options()

    # noinspection PyUnusedLocal
    async def async_step_init(self, user_input=None):
        """Manage the Exta Life options."""
        return await self.async_step_general()

    async def async_step_general(self, user_input=None):
        if user_input is not None:
            self.options[OPTIONS_GENERAL] = user_input
            return await self.async_step_light()

        return self.async_show_form(
            step_id=OPTIONS_GENERAL,
            data_schema=vol.Schema(
                {
                    vol.Required(OPTIONS_GENERAL_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): cv.positive_int,
                    vol.Required(OPTIONS_GENERAL_DISABLE_NOT_RESPONDING, default=True): bool
                }
            ),
        )

    async def async_step_light(self, user_input=None):
        if user_input is not None:
            self.options[OPTIONS_LIGHT] = user_input
            return await self.async_step_cover()

        return self.async_show_form(
            step_id=OPTIONS_LIGHT,
            data_schema=vol.Schema(
                {
                    vol.Required(OPTIONS_LIGHT_ICONS_LIST,
                                 default=self.options[OPTIONS_LIGHT]
                                 .get(OPTIONS_LIGHT_ICONS_LIST)): cv.multi_select(DEVICE_ICON_ARR_LIGHT)
                }
            ),
        )

    async def async_step_cover(self, user_input=None):
        if user_input is not None:
            self.options[OPTIONS_COVER] = user_input
            return self.async_create_entry(title="Exta Life Options", data=self.options)

        return self.async_show_form(
            step_id=OPTIONS_COVER,
            data_schema=vol.Schema(
                {
                    vol.Required("inverted_control", default=self.options[OPTIONS_COVER].get("inverted_control")): bool
                }
            ),
        )
