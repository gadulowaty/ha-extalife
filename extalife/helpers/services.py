""" definition of all services for this integration """
import asyncio
import logging
import voluptuous as vol
from homeassistant.const import CONF_ENTITY_ID
import homeassistant.helpers.entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .typing import CoreType

# services
SVC_RESTART = "restart"  # restart controller
SVC_REFRESH_STATE = "refresh_state"  # execute status refresh, fetch new status from controller

_LOGGER = logging.getLogger(__name__)

SCHEMA_BASE = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id
    }
)
SCHEMA_REFRESH_STATE = SCHEMA_RESTART = SCHEMA_BASE

SCHEMA_TEST_BUTTON = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required('button'): str,
        vol.Required('channel_id'): str,
        vol.Required('event'): str,
    }
)


class ExtaLifeServices:
    """ handle Exta Life services """

    def __init__(self, hass: HomeAssistant):
        self._hass = hass
        self._services = []

    def _get_core(self, entity_id: str) -> CoreType:
        """ Resolve the Core helper class """
        from .core import Core
        return Core.get(self._get_entry_id(entity_id))

    def _get_entry_id(self, entity_id: str):
        """ Resolve ConfigEntry.entry_id for entity_id """
        # registry = asyncio.run_coroutine_threadsafe(er.async_get_registry(self._hass), self._hass.loop).result()
        registry = er.async_get(self._hass)
        return registry.async_get(entity_id).config_entry_id

    async def async_register_services(self):
        """ register all Exta Life integration services """
        self._hass.services.async_register(DOMAIN, SVC_RESTART, self._handle_restart, SCHEMA_RESTART)
        self._services.append(SVC_RESTART)

        self._hass.services.async_register(DOMAIN, SVC_REFRESH_STATE, self._handle_refresh_state, SCHEMA_REFRESH_STATE)
        self._services.append(SVC_REFRESH_STATE)

        self._hass.services.async_register(DOMAIN, 'test_button', self._handle_test_button, SCHEMA_TEST_BUTTON)
        self._services.append('test_button')

    async def async_unregister_services(self):
        """ Unregister all Exta Life integration services """
        for service in self._services:
            self._hass.services.async_remove(DOMAIN, service)

    def _handle_restart(self, call):
        """ service: extalife.restart """
        entity_id = call.data.get(CONF_ENTITY_ID)

        core = self._get_core(entity_id)

        asyncio.run_coroutine_threadsafe(core.api.async_restart(), self._hass.loop)

    def _handle_refresh_state(self, call):
        """ service: extalife.refresh_state """
        entity_id = call.data.get(CONF_ENTITY_ID)

        core = self._get_core(entity_id)
        asyncio.run_coroutine_threadsafe(core.data_manager.async_execute_status_polling(), self._hass.loop)
        #  core.data_manager.async_execute_status_polling

    def _handle_test_button(self, call):
        from .common import PseudoPlatform

        button = call.data.get('button')
        entity_id = call.data.get(CONF_ENTITY_ID)
        channel_id = call.data.get('channel_id')
        event = call.data.get('event')

        data = {'button': button}
        core = self._get_core(entity_id)

        signal = PseudoPlatform.get_notif_upd_signal(channel_id)

        num = 0

        def click():
            nonlocal num
            seq = 1
            num += 1
            signal_data = {"button": button, 'click': num, 'sequence': seq, 'state': 1}
            core.async_signal_send_sync(signal, signal_data)

            signal_data = signal_data.copy()
            seq += 1
            signal_data['state'] = 0
            signal_data['sequence'] = seq

            core.async_signal_send_sync(signal, signal_data)

        if event == 'triple':
            click()
            click()
            click()

        elif event == 'double':
            click()
            click()

        elif event == 'single':
            click()

        elif event == 'down':
            data['state'] = 1
            core.async_signal_send_sync(signal, data)

        elif event == 'up':
            data['state'] = 0
            core.async_signal_send_sync(signal, data)
