"""Support for Exta Life devices firmware update notifications """
# important for log: curl -v --user-agent "" --user update:4Rjs#COQ00 http://extalife.cloud:4040/firmware/?list
import logging
from typing import (
    Any,
)

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
    DOMAIN as DOMAIN_UPDATE,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ExtaLifeChannel
from .helpers.core import Core

_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up Exta Life covers based on existing config."""

    core: Core = Core.get(config_entry.entry_id)
    channels: list[dict[str, Any]] = core.get_channels(DOMAIN_UPDATE)

    _LOGGER.debug("Discovery: %s", channels)
    if channels:
        async_add_entities(
            [ExtaLifeUpdate(channel_data, config_entry) for channel_data in channels]
        )

    core.pop_channels(DOMAIN_UPDATE)


class ExtaLifeUpdate(ExtaLifeChannel, UpdateEntity):
    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry):
        super().__init__(channel, config_entry)

        self._attr_device_class = UpdateDeviceClass.FIRMWARE

        self._attr_supported_features = UpdateEntityFeature.INSTALL
        self._attr_supported_features |= UpdateEntityFeature.BACKUP
        self._attr_supported_features |= UpdateEntityFeature.RELEASE_NOTES
