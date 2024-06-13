import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..pyextalife import (
    ExtaLifeAPI,
    ExtaLifeDeviceModel,
    ExtaLifeMap,
    PRODUCT_MANUFACTURER,
    PRODUCT_SERIES,
)
from .const import DOMAIN as DOMAIN, SIGNAL_NOTIF_STATE_UPDATED

from .device import Device

_LOGGER = logging.getLogger(__name__)


class PseudoPlatform:
    def __init__(self, config_entry: ConfigEntry, channel_data: dict[str, Any]):

        from .core import Core

        self._core: Core = Core.get(config_entry.entry_id)
        self._hass: HomeAssistant = self._core.get_hass()
        self._config_entry: ConfigEntry = config_entry
        self._channel_data = channel_data.get("data")
        self._id: str = channel_data.get("id")

        self._signal_data_notif_remove_callback = None

        # HA device id
        self._device: Device | None = None

    @property
    def controller(self) -> ExtaLifeAPI:
        """Return PyExtaLife's controller component associated with entity."""
        return self._core.api

    @property
    def id(self) -> str:
        return self._id

    @property
    def device_type(self) -> ExtaLifeDeviceModel:
        """ Exta Life device Type """
        return ExtaLifeDeviceModel(self._channel_data.get("type"))

    @property
    def device_info(self) -> dict[str, Any]:
        model_name: str = ExtaLifeMap.type_to_model_name(self.device_type)
        serial_no: int = self._channel_data.get('serial')
        return {
            "identifiers": {(DOMAIN, serial_no)},
            "name": f"{PRODUCT_MANUFACTURER} {PRODUCT_SERIES} {model_name}",
            "manufacturer": PRODUCT_MANUFACTURER,
            "model": model_name,
            "hw_version": None,
            "serial_number": f"{serial_no:06X}",
            "via_device": (DOMAIN, self.controller.mac),
        }

    def assign_device(self, device: Device) -> None:
        """ device : Device subclass """
        self._device = device

    @property
    def device(self) -> Device:
        return self._device

    @staticmethod
    def get_notif_upd_signal(ch_id) -> str:
        return f"{SIGNAL_NOTIF_STATE_UPDATED}_{ch_id}"

    async def async_added_to_hass(self) -> None:
        pass

    async def async_will_remove_from_hass(self) -> None:
        pass

    def _async_state_notif_update_callback(self, data) -> None:
        pass
