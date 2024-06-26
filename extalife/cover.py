"""Support for Exta Life roller shutters: SRP, SRM, ROB(future)"""
import logging
from typing import (
    Any,
)

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
    ATTR_POSITION,
    DOMAIN as DOMAIN_COVER,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers.const import (
    OPTIONS_COVER_INVERTED_CONTROL,
    DOMAIN_VIRTUAL_COVER_SENSOR
)
from .helpers.core import Core
from .helpers.entities import ExtaLifeChannelNamed
from .pyextalife import (
    ExtaLifeAction,
    ExtaLifeDeviceModel,
    DEVICE_ARR_COVER,
    DEVICE_ARR_SENS_GATE_CONTROLLER
)

GATE_CHN_TYPE_GATE = 0
GATE_CHN_TYPE_TILT_GATE = 1
GATE_CHN_TYPE_WICKET = 2
GATE_CHN_TYPE_MONO = 3

_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback) -> None:
    """Set up Exta Life covers based on existing config."""

    core: Core = Core.get(config_entry.entry_id)

    async def async_load_entities() -> None:

        channels: list[dict[str, Any]] = core.get_channels(DOMAIN_COVER)
        _LOGGER.debug(f"Discovery ({DOMAIN_COVER}): {channels}")
        if channels:
            async_add_entities([ExtaLifeCoverNamed(channel, config_entry) for channel in channels])

        core.pop_channels(DOMAIN_COVER)
        return None

    await core.platform_register(DOMAIN_COVER, async_load_entities)


class ExtaLifeCoverNamed(ExtaLifeChannelNamed, CoverEntity):
    """Representation of ExtaLife Cover"""

    def __init__(self, channel: dict[str, Any], config_entry: ConfigEntry):
        super().__init__(config_entry, channel)

        self.push_virtual_sensor_channels(DOMAIN_VIRTUAL_COVER_SENSOR, channel)

    # Exta Life extreme cover positions
    POS_CLOSED = 100
    POS_OPEN = 0

    @property
    def device_class(self) -> CoverDeviceClass:
        """Return the class of this device, from component DEVICE_CLASSES."""
        chn_type = self.channel_data.get("channel_type")
        if self.device_model in DEVICE_ARR_COVER:
            return CoverDeviceClass.SHUTTER
        elif chn_type == GATE_CHN_TYPE_WICKET:
            return CoverDeviceClass.DOOR
        else:
            return CoverDeviceClass.GATE

    @property
    def supported_features(self) -> CoverEntityFeature | int | None:
        """Flag supported features."""
        dev_type = self.channel_data.get("type")
        if not self.is_exta_free:
            if dev_type in DEVICE_ARR_COVER:
                features = (CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE |
                            CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP)
                return features
            elif dev_type in DEVICE_ARR_SENS_GATE_CONTROLLER:
                features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
                return features
        else:
            return CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    @property
    def current_cover_position(self) -> int | None:
        """Return current position of cover. 0 is closed, 100 is open."""
        # HA GUI buttons meaning:
        # ARROW UP   - open cover
        # ARROW DOWN - close cover
        # THIS CANNOT BE CHANGED AS IT'S HARDCODED IN HA GUI

        if (self.is_exta_free or self.device_class == CoverDeviceClass.GATE or
                self.device_class == CoverDeviceClass.DOOR):
            return

        val = self.channel_data.get("value")
        pos = val if self.is_inverted_control else 100-val

        _LOGGER.debug(f"current_cover_position for cover: {self.entity_id}. Model: {val}, returned to HA: {pos}")
        return pos

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        data = self.channel_data
        pos = int(kwargs.get(ATTR_POSITION))
        value = pos if self.is_inverted_control else 100-pos

        _LOGGER.debug(f"set_cover_position for cover: {self.entity_id}. From HA: {pos}, model: {value}")
        if await self.async_action(ExtaLifeAction.EXTA_LIFE_SET_POS, value=value):
            data["value"] = value
            self.async_schedule_update_ha_state()

    @property
    def is_inverted_control(self) -> bool:
        """Wherever to use inverted logic of open/close for 0-100"""
        return self.config_entry.options.get(DOMAIN_COVER).get(OPTIONS_COVER_INVERTED_CONTROL, False)

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed (affects roller icon and entity status)."""
        pos = self.channel_data.get("value")
        gate_state = self.channel_data.get("channel_state")

        if pos is not None:
            expect = ExtaLifeCoverNamed.POS_CLOSED
            _LOGGER.debug(f"is_closed for cover: {self.entity_id}. model: {pos}, returned to HA: {pos == expect}")
            return pos == expect

        if gate_state is not None:
            return gate_state == 3
        return None

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        data = self.channel_data
        # ROB-21 to open 'pos' must be different from 0
        if self.device_class == CoverDeviceClass.GATE or self.device_class == CoverDeviceClass.DOOR:
            pos = 1
        else:
            pos = ExtaLifeCoverNamed.POS_OPEN

        if not self.is_exta_free:
            if self.device_class != CoverDeviceClass.GATE and self.device_class != CoverDeviceClass.DOOR:
                action = ExtaLifeAction.EXTA_LIFE_SET_POS
            else:
                action = ExtaLifeAction.EXTA_LIFE_GATE_POS

            if await self.async_action(action, value=pos):
                data["value"] = pos
                _LOGGER.debug(f"open_cover for cover: {self.entity_id}. model: {pos}")
                self.async_schedule_update_ha_state()
        else:
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_UP_PRESS) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_UP_RELEASE)):
                self.async_schedule_update_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        data = self.channel_data
        pos = ExtaLifeCoverNamed.POS_CLOSED
        if not self.is_exta_free:
            if self.device_class != CoverDeviceClass.GATE and self.device_class != CoverDeviceClass.DOOR:
                action = ExtaLifeAction.EXTA_LIFE_SET_POS
            else:
                action = ExtaLifeAction.EXTA_LIFE_GATE_POS
            if await self.async_action(action, value=pos):
                data["value"] = pos
                _LOGGER.debug(f"close_cover for cover: {self.entity_id}. model: {pos}")
                self.async_schedule_update_ha_state()

        elif ExtaLifeDeviceModel(self.channel_data.get("type")) != ExtaLifeDeviceModel.ROB01:
            # ROB-01 supports only 1 toggle mode using 1 command
            if (await self.async_action(ExtaLifeAction.EXTA_FREE_DOWN_PRESS) and
                    await self.async_action(ExtaLifeAction.EXTA_FREE_DOWN_RELEASE)):
                self.async_schedule_update_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.async_action(ExtaLifeAction.EXTA_LIFE_STOP)

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """ React on state notification from controller """
        super().on_state_notification(data)

        ch_data = self.channel_data.copy()
        if ch_data.get("value") is not None:
            ch_data["value"] = data.get("value")
        if ch_data.get("channel_state") is not None:
            ch_data["channel_state"] = data.get("channel_state")
        # update only if notification data contains new status; prevent HA event bus overloading
        if ch_data != self.channel_data:
            self.channel_data.update(ch_data)

            # synchronize DataManager data with processed update & entity data
            self.sync_data_update_ha()
