"""Support for ExtaLife devices."""
import datetime
import logging
from contextlib import suppress
from datetime import timedelta
from typing import (
    Any,
    Callable,
    Mapping,
)

import homeassistant.helpers.translation
import voluptuous as vol
from homeassistant.components.binary_sensor import DOMAIN as DOMAIN_BINARY_SENSOR
from homeassistant.components.button import DOMAIN as DOMAIN_BUTTON
from homeassistant.components.climate import DOMAIN as DOMAIN_CLIMATE
from homeassistant.components.cover import DOMAIN as DOMAIN_COVER
from homeassistant.components.light import DOMAIN as DOMAIN_LIGHT
from homeassistant.components.sensor import DOMAIN as DOMAIN_SENSOR
from homeassistant.components.switch import DOMAIN as DOMAIN_SWITCH
from homeassistant.components.update import DOMAIN as DOMAIN_UPDATE
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    ConfigEntryAuthFailed,
)
from homeassistant.helpers import (
    device_registry as dr,
    config_validation as cv,
    entity_platform,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import DEFAULT_SCAN_INTERVAL
from homeassistant.helpers.typing import ConfigType

from .config_flow import get_default_options
from .helpers.const import (
    DOMAIN,
    CONF_CONTROLLER_IP,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_VER_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VER_INTERVAL,
    OPTIONS_COVER_INVERTED_CONTROL,
    SIGNAL_DATA_UPDATED,
    SIGNAL_CHANNEL_NOTIF_STATE_UPDATED,
    SIGNAL_DEVICE_NOTIF_CONFIG_UPDATED,
    DOMAIN_TRANSMITTER,
    CONF_OPTIONS,
    OPTIONS_LIGHT,
    OPTIONS_LIGHT_ICONS_LIST,
    OPTIONS_COVER,
    OPTIONS_GENERAL,
    OPTIONS_GENERAL_POLL_INTERVAL,
    OPTIONS_GENERAL_VER_INTERVAL,
    OPTIONS_GENERAL_DISABLE_NOT_RESPONDING,
    VIRTUAL_SENSOR_CHN_FIELD,
    VIRTUAL_SENSOR_DEV_CLS,
    VIRTUAL_SENSOR_PATH,
    VIRTUAL_SENSOR_ALLOWED_CHANNELS
)
from .helpers.core import Core
from .pyextalife import (
    ExtaLifeAPI,
    ExtaLifeCmd,
    ExtaLifeConnParams,
    ExtaLifeData,
    ExtaLifeDeviceModel,
    ExtaLifeDeviceModelName,
    ExtaLifeMap,
    ExtaLifeError,
    ExtaLifeCmdError,
    DEVICE_ARR_ALL_SWITCH,
    DEVICE_ARR_ALL_LIGHT,
    DEVICE_ARR_ALL_COVER,
    DEVICE_ARR_ALL_CLIMATE,
    DEVICE_ARR_ALL_SENSOR_MEAS,
    DEVICE_ARR_ALL_SENSOR_BINARY,
    DEVICE_ARR_ALL_SENSOR_MULTI,
    DEVICE_ARR_ALL_TRANSMITTER,
    DEVICE_ARR_ALL_IGNORE,
    PRODUCT_MANUFACTURER,
    PRODUCT_SERIES_EXTA_LIFE,
    PRODUCT_SERIES_EXTA_FREE,
    EFC01_EXTA_APP_ID
)

_LOGGER = logging.getLogger(__name__)

OPTIONS_DEFAULTS = get_default_options()

# schema validations
OPTIONS_CONF_SCHEMA = {
    vol.Optional(OPTIONS_GENERAL, default=OPTIONS_DEFAULTS[OPTIONS_GENERAL]): {
        vol.Optional(
            OPTIONS_GENERAL_POLL_INTERVAL,
            default=OPTIONS_DEFAULTS[OPTIONS_GENERAL][OPTIONS_GENERAL_POLL_INTERVAL],
        ): cv.positive_int,
        vol.Optional(
            OPTIONS_GENERAL_VER_INTERVAL,
            default=OPTIONS_DEFAULTS[OPTIONS_GENERAL][OPTIONS_GENERAL_VER_INTERVAL],
        ): cv.positive_int,
    },
    vol.Optional(OPTIONS_LIGHT, default=OPTIONS_DEFAULTS[OPTIONS_LIGHT]): {
        vol.Optional(
            OPTIONS_LIGHT_ICONS_LIST,
            default=OPTIONS_DEFAULTS[OPTIONS_LIGHT][OPTIONS_LIGHT_ICONS_LIST],
        ): cv.ensure_list,
    },
    vol.Optional(OPTIONS_COVER, default=OPTIONS_DEFAULTS[OPTIONS_COVER]): {
        vol.Optional(
            OPTIONS_COVER_INVERTED_CONTROL,
            default=OPTIONS_DEFAULTS[OPTIONS_COVER][OPTIONS_COVER_INVERTED_CONTROL],
        ): cv.boolean,
    },
}


# noinspection PyUnusedLocal
async def async_migrate_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug(f"Migrating from version {config_entry.version}")

    #  Flatten configuration but keep old data if user rollbacks HASS
    if config_entry.version == 1:

        options = {**config_entry.options}
        options.setdefault(
            OPTIONS_GENERAL,
            {
                OPTIONS_GENERAL_POLL_INTERVAL: config_entry.data.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                ),
                OPTIONS_GENERAL_VER_INTERVAL: config_entry.data.get(
                    CONF_VER_INTERVAL, DEFAULT_VER_INTERVAL
                )
            },
        )
        config_entry.options = {**options}

        new = {**config_entry.data}
        try:
            new.pop(CONF_POLL_INTERVAL)
            # get rid of erroneously migrated options from integration 1.0
            new.pop(CONF_OPTIONS)
        except KeyError:  # pylint: disable=bare-except
            pass
        config_entry.data = {**new}

        config_entry.version = 2

    _LOGGER.info(f"Migration to version {config_entry.version} successful")

    return True


# noinspection PyUnusedLocal
async def async_setup(
        hass: HomeAssistant,
        hass_config: ConfigType) -> bool:
    """Set up Exta Life component from configuration.yaml. This will basically
    forward the config to a Config Flow and will migrate to Config Entry"""

    _LOGGER.debug(f"hass_config: {hass_config}")

    if not hass.config_entries.async_entries(DOMAIN) and DOMAIN in hass_config:
        hass.data.setdefault(DOMAIN, {CONF_OPTIONS: hass_config[DOMAIN].get(CONF_OPTIONS, None)})
        _LOGGER.debug(f"async_setup, hass.data.domain: {hass.data.get(DOMAIN)}")

        result = hass.async_create_task(  # pylint: disable=unused-variable
            hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data=hass_config[DOMAIN])
        )

    return True


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Set up Exta Life component from a Config Entry"""

    _LOGGER.debug(f"async_setup_entry(): starting for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    hass.data.setdefault(DOMAIN, {})
    Core.create(hass, config_entry)
    result = await initialize(hass, config_entry)

    _LOGGER.debug(f"async_setup_entry(): finished for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    return result


# noinspection PyUnusedLocal
async def async_unload_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Unload a config entry: unload platform entities, stored data, deregister signal listeners"""

    _LOGGER.debug(f"async_unload_entry(): starting for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    core = Core.get(config_entry.entry_id)
    result = await core.unload_entry_from_hass()

    _LOGGER.debug(f"async_unload_entry(): finished for '{config_entry.title}' (entry_id='{config_entry.entry_id}')")

    return result


async def initialize(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Initialize Exta Life integration based on a Config Entry"""

    def init_options() -> None:
        """Populate default options for Exta Life."""

        default = get_default_options()
        options = {**config_entry.options}
        # migrate options after creation of ConfigEntry
        if not options:
            yaml_conf = hass.data.get(DOMAIN)
            yaml_options = None
            if yaml_conf is not None:
                yaml_options = yaml_conf.get(CONF_OPTIONS)

            _LOGGER.debug(f"init_options, yaml_options {yaml_options}")

            options = default if yaml_options is None else yaml_options

        # set default values if something is missing
        options_def = options.copy()
        for k, v in default.items():
            options_def.setdefault(k, v)

        # check for changes and if options should be persisted
        if options_def != options or not config_entry.options:
            hass.config_entries.async_update_entry(config_entry, options=options_def)

    init_options()

    core = Core.get(config_entry.entry_id)

    controller = core.api
    username = config_entry.data[CONF_USERNAME]
    password = config_entry.data[CONF_PASSWORD]
    controller_ip: str = config_entry.data[CONF_CONTROLLER_IP]

    _LOGGER.debug(f"ExtaLife initializing '{config_entry.title}'... "
                  f"[Debugger attached: {"YES" if ExtaLifeAPI.is_debugger_active() else "NO"}]")

    if controller_ip:
        _LOGGER.debug(f"Trying to connect to controller using IP: {controller_ip}")
        controller_host, controller_port = ExtaLifeConnParams.get_host_and_port(controller_ip)
        autodiscover: bool = False
    else:
        _LOGGER.info("Controller IP is not specified. Will use autodiscovery mode")
        controller_host = ""
        controller_port = 0
        autodiscover: bool = True

    # try to connect and logon to controller
    try:
        await controller.async_connect(username, password, controller_host, controller_port,
                                       timeout=5.0, autodiscover=autodiscover)

    except ExtaLifeError as err:
        if isinstance(err, ExtaLifeCmdError):
            raise ConfigEntryAuthFailed(err.message)
        else:
            _LOGGER.error(f"Unable to connect to EFC-01 @ {controller_ip}, {err.message}")
            raise ConfigEntryNotReady

        # await core.unload_entry_from_hass()
        # return False

    if controller_ip is None or (controller.host != controller_host) or (controller.port != controller_port):
        # passed controller ip has changed during autodiscovery
        # should store new controller.host to HA configuration
        cur_data = {**config_entry.data}
        cur_data.update({CONF_CONTROLLER_IP: ExtaLifeConnParams.get_addr(controller.host, controller.port)})
        hass.config_entries.async_update_entry(config_entry, data=cur_data)
        _LOGGER.info(f"Controller IP updated to: {controller.host}")

    if controller.version_installed is not None:
        _LOGGER.debug(f"EFC-01 Software version: {controller.version_installed}")
    else:
        _LOGGER.error("Error communicating with the EFC-01 controller.")
        return False

    await core.register_controller()

    # publish services to HA service registry
    await core.async_register_services()

    _LOGGER.info(f"Exta Life integration setup for '{config_entry.title}' finished successfully!")
    return True


async def async_get_notification(
        hass: HomeAssistant,
        translation_domain: str,
        translation_key: str,
        translation_placeholders: dict[str, str] | None = None,
) -> str:
    """Return a translated exception message.

    Defaults to English, requires translations to already be cached.
    """
    language = hass.config.language
    localize_key = (
        f"component.{translation_domain}.notifications.{translation_key}"
    )

    translations = await homeassistant.helpers.translation.async_get_translations(hass, language, "notifications")
    if localize_key in translations:
        if message := translations[localize_key]:
            message = message.rstrip(".")
        if not translation_placeholders:
            return message
        with suppress(KeyError):
            message = message.format(**translation_placeholders)
        return message

    # We return the translation key when was not found in the cache
    return translation_key


class ChannelDataManager:
    """Get the latest data from EFC-01, call device discovery, handle status notifications."""

    def __init__(self, core: Core, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the Channel Data Manager object."""

        self._core: Core = core
        self._hass: HomeAssistant = hass
        self._config_entry: ConfigEntry = config_entry

        self._channels_data: dict[str, dict[str, Any]] = {}
        self._devices_data: dict[int, dict[str, Any]] = {}

        self._channels_known: list[str] = []
        self._status_polling_task_stop: Callable[[], None] | None = None
        self._version_polling_task_stop: Callable[[], None] | None = None

    def _channel_known(self, channel_id: str) -> bool:
        """append channel_id to list of known channels
        returns true if channel is not known and false otherwise"""

        if channel_id not in self._channels_known:
            self._channels_known.append(channel_id)
            return False
        return True

    def channel_get_data(self, channel_id: str) -> dict[str, Any] | None:
        """get data associated with requested channel_id"""

        # channel data manager contains PyExtaLife API channel data dict value pair: {("id"): ("data")}
        return self._channels_data.get(channel_id)

    def channel_update_data(self, channel_id: str, channel_data: dict[str, Any]) -> None:
        """Update data of a channel e.g. after notification data received and processed
        by an entity"""

        self._channels_data.update({channel_id: channel_data})

    def channel_on_notify(self, data: ExtaLifeData) -> None:
        # TODO: missing one-liner

        _LOGGER.debug(f"Received channel status change notification from controller: {data}")

        channel_id: str = ExtaLifeAPI.device_make_channel_id(data)

        # inform HA entity of state change via notification
        signal: str = ExtaLifeChannel.signal_get_channel_notification_id(channel_id)
        if ExtaLifeAPI.device_has_sub_channels(channel_id):
            self._core.async_signal_send(signal, data)
        else:
            self._core.async_signal_send_sync(signal, data)

    def devices_get(
            self, device_filter: Callable[[dict[str, Any]], bool] | None = None
    ) -> dict[int, dict[str, Any]]:
        # TODO: missing one-liner

        if device_filter:
            result: dict[int, dict[str, Any]] = {}
            for device_id, device_data in self._devices_data:
                if device_filter(device_data):
                    result.setdefault(device_id, device_data)
            return result

        return self._devices_data

    def device_get_data(self, device_id: int) -> dict[str, Any] | None:
        # TODO: missing-oneliner

        return self._devices_data.get(device_id)

    def device_update_data(self, device_id: int, device_data: dict[str, Any]) -> None:
        """Update data of a device e.g. after notification data received and processed
        by an entity"""

        self._devices_data.update({device_id: device_data})

    def device_register(
            self, device_id: int, device_type: ExtaLifeDeviceModel, serial_no: int
    ) -> dict[str, Any] | None:
        # TODO: missing one-liner

        if device_id not in self._devices_data.keys():
            device_data: dict[str, Any] = {"id": device_id, "type": device_type, "serial": serial_no}
            self._devices_data.update({device_id: device_data})
            return device_data

        return None

    def device_on_notify(self, data: ExtaLifeData) -> None:
        # TODO: missing one-liner

        _LOGGER.debug(f"on_device_notify: Received device config change notification: {data}")

        device_id = data.get("id", -1)
        signal: str = ExtaLifeDevice.signal_get_device_notification_id(device_id)

        # inform HA entity of state change via notification
        self._core.async_signal_send(signal, data)

    async def async_status_polling_task_setup(self, poll_now: bool = True, poll_periodic: bool = True) -> None:
        """Executes status polling triggered externally, not via periodic callback + resets next poll time"""

        self._status_polling_task_remove()

        if poll_now:
            await self._async_status_polling_task()

        if poll_periodic:
            self._status_polling_task_configure()

    def _status_polling_task_remove(self) -> None:
        """Stop status polling task scheduler"""

        if self._status_polling_task_stop is not None:
            self._status_polling_task_stop()
            _LOGGER.debug(f"[{self._core.config_entry.title}] Status polling task has been removed")

        self._status_polling_task_stop = None

    def _status_polling_task_configure(self) -> None:
        """(Re)set periodic callback for status polling based on interval from integration options"""

        # register callback for periodic status update polling + device discovery
        status_poll_interval: int = self._config_entry.options.get(OPTIONS_GENERAL).get(
            OPTIONS_GENERAL_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )

        _LOGGER.debug(f"[{self._core.config_entry.title}] Periodic status poll task interval "
                      f"has been set to {status_poll_interval} minute(s)")
        self._status_polling_task_stop = self._core.async_track_time_interval(
            self._async_status_polling_task, timedelta(minutes=status_poll_interval)
        )

    # noinspection PyUnusedLocal
    async def _async_status_polling_task(self, now: datetime = None) -> None:
        """Get the latest device&channel status data from EFC-01.
        This method is called from HA task scheduler via async_track_time_interval"""

        # use Exta Life TCP communication class
        _LOGGER.debug(f"[{self._core.config_entry.title}] Executing EFC-01 status polling task")

        # if connection error or other - will receive None
        # otherwise it contains a list of channels
        channels: list[dict[str, Any]] = await self._core.api.async_get_channels()
        if channels is None or len(channels) == 0:
            _LOGGER.warning(f"[{self._core.config_entry.title}] No Channels could be obtained from the controller")
            return

        # create indexed access: dict from list element
        # dict key = "data" section
        for channel in channels:
            self.channel_update_data(channel["id"], channel["data"])

        self._core.async_signal_send(SIGNAL_DATA_UPDATED)

        _LOGGER.debug(f"[{self._core.config_entry.title}] Status for {len(self._channels_data)} channel(s) updated")

        await self._async_discover_devices()

    async def _async_discover_devices(self) -> None:
        """Fetch / refresh device data & discover devices and register them in Home Assistant."""

        def device_register(_exta_app_id: int, _device_type: ExtaLifeDeviceModel, _serial_no: int) -> bool:

            device_data = self.device_register(_exta_app_id, _device_type, _serial_no)
            if device_data:
                restartable: bool = (_device_type == ExtaLifeDeviceModel.EFC01)

                updatable: bool = (_device_type not in DEVICE_ARR_ALL_TRANSMITTER and
                                   _device_type < ExtaLifeDeviceModel.EXTA_FREE_FIRST)
                _LOGGER.debug(f"[{self._core.config_entry.title}] Found new device: "
                              f"serial_no={_serial_no:06x}; type={_device_type.name}, "
                              f"update={"YES" if updatable else "NO"}")

                if updatable:
                    std_platforms_channels.setdefault(DOMAIN_UPDATE, []).append(device_data)
                if restartable:
                    std_platforms_channels.setdefault(DOMAIN_BUTTON, []).append(device_data)
                return True

            return False

        std_platforms_channels: dict[str, list[dict[str, Any]]] = {}
        usr_platforms_channels: dict[str, list[dict[str, Any]]] = {}

        entities: int = 0
        devices: int = 0
        if device_register(EFC01_EXTA_APP_ID, ExtaLifeDeviceModel.EFC01, self._core.api.serial_no):
            devices += 1

        light_icons_list: list[int] = self._config_entry.options.get(DOMAIN_LIGHT).get(OPTIONS_LIGHT_ICONS_LIST)

        # get data from the ChannelDataManager object stored in HA object data
        for channel_id, channel_data in self._channels_data.items():  # -> dict id:data

            # do discovery only for newly discovered devices and not known devices
            if self._channel_known(channel_id):
                continue

            channel: dict[str, Any] = {"id": channel_id, "data": channel_data}
            device_id: int = channel_data.get("id")
            device_type: ExtaLifeDeviceModel = ExtaLifeDeviceModel(channel_data.get("type"))
            serial_no: int = channel_data.get("serial")
            platform_name: str = ""

            # this channel is updatable add to list
            devices += 1 if device_register(device_id, device_type, serial_no) else 0

            # skip some devices that are not to be shown nor controlled by HA
            if device_type in DEVICE_ARR_ALL_IGNORE:
                continue

            if device_type in DEVICE_ARR_ALL_SWITCH:
                platform_name = DOMAIN_LIGHT if channel["data"]["icon"] in light_icons_list else DOMAIN_SWITCH

            elif device_type in DEVICE_ARR_ALL_LIGHT:
                platform_name = DOMAIN_LIGHT

            elif device_type in DEVICE_ARR_ALL_COVER:
                platform_name = DOMAIN_COVER

            elif device_type in DEVICE_ARR_ALL_SENSOR_MEAS:
                platform_name = DOMAIN_SENSOR

            elif device_type in DEVICE_ARR_ALL_SENSOR_BINARY:
                platform_name = DOMAIN_BINARY_SENSOR

            elif device_type in DEVICE_ARR_ALL_SENSOR_MULTI:
                platform_name = DOMAIN_SENSOR

            elif device_type in DEVICE_ARR_ALL_CLIMATE:
                platform_name = DOMAIN_CLIMATE

            elif device_type in DEVICE_ARR_ALL_TRANSMITTER:
                usr_platforms_channels.setdefault(DOMAIN_TRANSMITTER, []).append(channel)
                continue

            if not platform_name:
                _LOGGER.warning(f"Unsupported device type: {device_type}, channel id: {channel["id"]}")
                continue

            std_platforms_channels.setdefault(platform_name, []).append(channel)
            entities += 1

        _LOGGER.debug(f"Discovery found {entities} entities and {devices} device(s)")

        # can happen we don't have any sensors, so we need to put an empty list to trigger
        # creation of virtual sensors (if any) for
        std_platforms_channels.setdefault(DOMAIN_SENSOR, [])

        # sensors must be last as platforms will delegate their attributes to virtual sensors
        std_platforms_channels[DOMAIN_SENSOR] = std_platforms_channels.pop(DOMAIN_SENSOR)

        # this list will contain all platforms that require setup
        platforms: list[str] = []
        for platform_name, channels in std_platforms_channels.items():
            # store array of channels (variable 'channels') for each platform
            self._core.push_channels(platform_name, channels)
            # check if platform has been loaded. If not add to list if platform requiring
            # setup, otherwise load oper already added new channels for platform
            if not await self._core.platform_load(platform_name):
                platforms.append(platform_name)

        if platforms:
            # 'sync' call to synchronize channels' stack with platform setup
            _LOGGER.debug(f"Forward setup for {platforms}")
            await self._hass.config_entries.async_forward_entry_setups(self._config_entry, platforms)

        # setup pseudo-platforms
        for platform_name, channels in usr_platforms_channels.items():
            # store array of channels (variable 'channels') for each platform
            self._core.push_channels(platform_name, channels, True)
            self._hass.async_create_task(self._core.async_setup_custom_platform(platform_name))

    async def async_version_polling_task_setup(self, poll_now: bool = True, poll_periodic: bool = True) -> None:
        """Executes version polling triggered externally, not via periodic callback + resets next poll time"""

        self._version_polling_task_remove()

        if poll_now:
            await self._async_version_polling_task()

        if poll_periodic:
            self._version_polling_task_configure()

    async def async_version_polling_task_run(self) -> None:

        self._version_polling_task_remove(False)

        await self._async_version_polling_task()

        self._version_polling_task_configure(False)

    def _version_polling_task_configure(self, set_next_check: bool = True) -> None:
        """(Re)set periodic callback for version polling"""

        version_poll_interval: int = 10

        _LOGGER.debug(f"[{self._core.config_entry.title}] Periodic version poll task interval has "
                      f"been set to {version_poll_interval} minutes(s)")
        self._version_polling_task_stop = self._core.async_track_time_interval(
            self._async_version_polling_task, timedelta(minutes=version_poll_interval)
        )
        if set_next_check:
            self._core.ver_check_set(580)

    def _version_polling_task_remove(self, unset_next_check: bool = True) -> None:
        """Stop version polling task scheduler"""

        if self._version_polling_task_stop is not None:
            self._version_polling_task_stop()
            _LOGGER.debug(f"[{self._core.config_entry.title}] version polling task has been removed")
        if unset_next_check:
            self._core.ver_check_set(-1)
        self._version_polling_task_stop = None

    # noinspection PyUnusedLocal
    async def _async_version_polling_task(self, now: datetime = None) -> None:
        """Get the latest device config setup from EFC-01.
        This method is called from HA task scheduler via async_track_time_interval"""

        if now is not None and not self._core.ver_check_required():
            return

        try:
            _LOGGER.debug(f"[{self._core.config_entry.title}] Executing EFC-01 version polling task")

            for device_id, device_data in self.devices_get().items():

                if device_id == EFC01_EXTA_APP_ID:
                    config_data = await self._core.api.async_check_version(self._core.ver_check_web)
                else:
                    config_data = await self._core.api.async_get_dev_config_details(device_id)

                if config_data:
                    config_data.update({"command": ExtaLifeCmd.FETCH_RECEIVER_CONFIG_DETAILS})
                    self.device_on_notify(config_data)
        finally:
            version_poll_interval: int = self._config_entry.options.get(OPTIONS_GENERAL).get(
                OPTIONS_GENERAL_VER_INTERVAL, DEFAULT_VER_INTERVAL
            )
            next_check: int = version_poll_interval * 3600 if now is not None else 0
            self._core.ver_check_set(next_check, True)

        return None


class ExtaLifeEntity(Entity):
    _attr_has_entity_name = True
    _attr_translation_key = DOMAIN

    def __init__(self, config_entry: ConfigEntry, data: dict[str, Any]):
        """Channel data -- channel information from PyExtaLife."""

        self._config_entry: ConfigEntry = config_entry
        self._core: Core = Core.get(config_entry.entry_id)
        self._data: dict[str, Any] = data
        self._data_available = True
        self._device_id: int = data.get("id", 0)
        self._device_model: ExtaLifeDeviceModel = ExtaLifeDeviceModel(data.get("type"))
        self._serial_no: int = data.get("serial")

        self._assumed_on: bool = False
        self._attr_has_entity_name = True
        self._attr_translation_key = DOMAIN

    def _set_data(self, data: dict[str, Any] | None) -> None:
        """store new data to entity"""

        _LOGGER.debug(f"async_update() for entity: {self.entity_id}, data to be updated: {data}")
        if data is None:
            self._data_available = False
            return

        self._data_available = True
        self._data.update(data)

    @staticmethod
    def _extra_state_attribute_update(src: dict[str, Any], dst: dict[str, Any], key: str):
        if src.get(key) is not None:
            dst.update({key: src.get(key)})

    @staticmethod
    def _mapping_to_dict(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(mapping) if mapping is not None else {}

    async def async_update(self) -> None:
        """Call to update state."""

    def _get_unique_id(self) -> str:
        """Provide unique id for HA entity registry"""
        return f"{DOMAIN}-{self.data.get("serial")}"

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """must be overridden in entity subclasses"""

    def get_placeholder(self) -> dict[str, str]:
        return {}

    @property
    def channel_manager(self) -> ChannelDataManager:
        """Return ChannelDataManager object"""
        return self.core.channel_manager

    @property
    def config_entry(self) -> ConfigEntry:
        return self._config_entry

    @property
    def controller(self) -> ExtaLifeAPI:
        """Return PyExtaLife's controller component associated with entity."""
        return self.core.api

    @property
    def core(self) -> Core:
        return self._core

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    @property
    def data_available(self) -> bool:
        return self._data_available

    @property
    def device_id(self) -> int:
        return self._device_id

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device specific attributes."""

        prod_series = (PRODUCT_SERIES_EXTA_FREE if self.is_exta_free else PRODUCT_SERIES_EXTA_LIFE)
        serial_no = self.data.get("serial", 0)
        return DeviceInfo(
            identifiers={(DOMAIN, str(serial_no))},
            name=f"{PRODUCT_MANUFACTURER} {prod_series} {self.device_model_name}",
            manufacturer=PRODUCT_MANUFACTURER,
            model=self.device_model_name,
            serial_number=f"{serial_no:06X}"
        )

    @property
    def device_model(self) -> ExtaLifeDeviceModel:
        """Return device type"""
        return self._device_model

    @property
    def device_model_name(self) -> ExtaLifeDeviceModelName:
        """Return model"""
        return ExtaLifeMap.type_to_model_name(self._device_model)

    @property
    def is_exta_free(self) -> bool:
        return self._device_model >= ExtaLifeDeviceModel.EXTA_FREE_FIRST

    @property
    def should_poll(self) -> bool:
        """
        Turn off HA polling in favour of update-when-needed status changes.
        Updates will be passed to HA by calling async_schedule_update_ha_state() for each entity
        """
        return False

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._get_unique_id()


class ExtaLifeDevice(ExtaLifeEntity):

    def __init__(self, config_entry: ConfigEntry, device: dict[str, Any]):
        # TODO: missing one-liner

        super().__init__(config_entry, device)

    def _get_unique_id(self) -> str:
        """Provide unique id for HA entity registry"""

        super_id = super()._get_unique_id()
        return f"{super_id}-{self.device_id}"

    async def async_update(self) -> None:
        """Call to update state."""

        await super().async_update()

        # read "data" section/dict by channel id
        data = self.channel_manager.device_get_data(self.device_id)

        self._set_data(data)

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """must be overridden in entity subclasses"""

    @staticmethod
    def signal_get_device_notification_id(device_id: int) -> str:
        return f"{SIGNAL_DEVICE_NOTIF_CONFIG_UPDATED}-{device_id}"

    def sync_data_update_ha(self) -> None:
        """Performs update of Channel Data Manager with Device data and calls HA state update.
        This is useful e.g. when Entity receives notification update, processes it and
        then must update its state. For consistency reasons - Channel Data Manager is updated and then
        HA status update is scheduled"""

        self.channel_manager.device_update_data(self.device_id, self.data)
        self.async_schedule_update_ha_state(True)


class ExtaLifeChannel(ExtaLifeEntity):
    """Base class of a ExtaLife Channel (an equivalent of HA's Entity).
    ParentEntity - instance of Parent Entity which instantiates this entity
    add_entity_cb - HA callback for adding entity in entity registry
    """

    def __init__(self, config_entry: ConfigEntry, channel: dict[str, Any]):
        """Channel data -- channel information from PyExtaLife."""

        super().__init__(config_entry, channel.get("data"))

        self._channel_id: str = channel.get("id")

    @staticmethod
    def _format_state_attr(attr: dict[str, Any]) -> dict[str, Any]:
        """Format state attributes based on name and other criteria.
        Can be overridden in dedicated subclasses to refine formatting"""
        from re import search

        for k, v in attr.items():
            val = v
            if search("voltage", k):
                v = v / 100
            elif search("current", k):
                v = v / 1000
            elif search("energy_consumption", k):
                v = v / 100000
            elif search("frequency", k):
                v = v / 100
            elif search("phase_shift", k):
                v = v / 10
            elif search("phase_energy", k):
                v = v / 100000
            if val != v:
                attr.update({k: v})
        return attr

    @staticmethod
    def signal_get_channel_notification_id(channel_id: str) -> str:
        return f"{SIGNAL_CHANNEL_NOTIF_STATE_UPDATED}-{channel_id}"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        await super().async_added_to_hass()

    async def async_update(self) -> None:
        """Call to update state."""

        await super().async_update()

        # read "data" section/dict by channel id
        data = self.channel_manager.channel_get_data(self.channel_id)

        self._set_data(data)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()

    def _get_unique_id(self) -> str:
        """Provide unique id for HA entity registry"""

        super_id = super()._get_unique_id()
        return f"{super_id}-{self.channel_id}"

    def sync_data_update_ha(self) -> None:
        """Performs update of Channel Data Manager with Entity data and calls HA state update.
        This is useful e.g. when Entity receives notification update, processes it and
        then must update its state. For consistency reasons - Channel Data Manager is updated and then
        HA status update is scheduled"""

        self.channel_manager.channel_update_data(self.channel_id, self.channel_data)
        self.async_schedule_update_ha_state(True)

    @property
    def assumed_state(self) -> bool:
        """Returns boolean if entity status is assumed status"""
        ret = self.is_exta_free
        _LOGGER.debug(f"Assumed state for entity: {self.entity_id}, {ret}")
        return ret

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_timeout = (
            self.channel_data.get("is_timeout")
            if self.config_entry.options.get(OPTIONS_GENERAL_DISABLE_NOT_RESPONDING)
            else False
        )
        _LOGGER.debug(f"available() for entity: {self.entity_id}. "
                      f"self.data_available: {self.data_available}; 'is_timeout': {is_timeout}")

        return self.data_available is True and is_timeout is False

    @property
    def channel_data(self) -> dict[str, Any]:
        return self.data

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def device_info(self) -> DeviceInfo | None:
        """Register device in Device Registry"""
        device_info = super().device_info
        device_info.setdefault("via_device", (DOMAIN, self.controller.mac))
        # device_info.update({"sw_version": "0.0.0"})
        return device_info

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return state attributes"""
        es_attr: dict[str, Any] = self._mapping_to_dict(super().extra_state_attributes)
        es_attr.update(
            {
                "channel_id": self.channel_id,
                "not_responding": self.channel_data.get("is_timeout")
            }
        )
        return es_attr

    @property
    def is_exta_free(self) -> bool:
        """Returns boolean if entity represents Exta Free device"""
        exta_free_device = self.channel_data.get("exta_free_device")
        if exta_free_device is None or not bool(exta_free_device):
            return False
        return True


class ExtaLifeChannelNamed(ExtaLifeChannel):

    def __init__(self, config_entry: ConfigEntry, channel: dict[str, Any]):
        super().__init__(config_entry, channel)

    async def _async_state_notif_update_callback(self, *args: Any) -> None:
        """Inform HA of state change received from controller status notification"""
        data = args[0]
        _LOGGER.debug(f"State update notification callback for entity id: {self.entity_id}, data: {data}")

        self.on_state_notification(data)

    async def _async_update_callback(self) -> None:
        """Inform HA of state update when receiving signal from channel data manager"""

        _LOGGER.debug(f"Update callback for entity id: {self.entity_id}")
        self.async_schedule_update_ha_state(True)

    def _get_virtual_sensors(self) -> list[dict[str, Any]]:
        """By default, check all entity attributes and return virtual sensor config"""
        from .sensor import MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS

        attr: list[dict[str, Any]] = []
        for k, v in self.channel_data.items():  # pylint: disable=unused-variable
            dev_class = MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS.get(k)
            if dev_class:

                if not self.is_virtual_sensor_allowed(k):
                    continue

                attr.append(
                    {
                        VIRTUAL_SENSOR_DEV_CLS: dev_class,
                        VIRTUAL_SENSOR_PATH: k
                    }
                )

        # get additional sensors returned by specific platform
        platform_sensors = self.virtual_sensors
        if platform_sensors:
            attr.extend(platform_sensors)

        return attr

    async def async_action(self, action, **add_pars: Any) -> dict[str, Any] | None:
        """Run controller command/action. Actions are currently hardcoded in platforms"""

        _LOGGER.debug(f"Executing action '{action}' on channel {self.channel_id}, params: {add_pars}")

        return await self.controller.async_execute_action(action, self.channel_id, **add_pars)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        await super().async_added_to_hass()

        _LOGGER.debug(f"async_added_to_hass: entity: {self.entity_id}")
        # register entity in Core for receiving all data updated notification
        self.core.async_signal_register(SIGNAL_DATA_UPDATED, self._async_update_callback)

        # register entity in Core for receiving entity own data updated notification
        self.core.async_signal_register(
            self.signal_get_channel_notification_id(self.channel_id),
            self._async_state_notif_update_callback,
        )

    def is_virtual_sensor_allowed(self, attr_name: str) -> bool:
        """Check if virtual sensor should be created for an attribute based on settings"""
        from .sensor import VIRTUAL_SENSOR_RESTRICTIONS

        channel = self.channel_data.get("channel")
        restr = VIRTUAL_SENSOR_RESTRICTIONS.get(attr_name)

        if restr:
            if not (channel in restr.get(VIRTUAL_SENSOR_ALLOWED_CHANNELS)):
                return False

        return True

    def push_virtual_sensor_channels(self, virtual_sensor_domain: str, channel_data: dict[str, Any]):
        """Push additional, virtual sensor channels for entity attributes. These should be
        processed by all platforms during platform setup and ultimately sensor entities
        shouldbe created by the sensor platform"""

        virtual_sensors = self._get_virtual_sensors()
        if len(virtual_sensors):
            _LOGGER.debug(f"Virtual sensors: {virtual_sensors}")
            for virtual in virtual_sensors:
                v_channel_data = channel_data.copy()
                v_channel_data.update({VIRTUAL_SENSOR_CHN_FIELD: virtual})
                self.core.push_channels(virtual_sensor_domain, [v_channel_data], append=True, custom=True)

    @property
    def name(self) -> str | None:
        """Return name of the entity"""
        return self.channel_data["alias"]

    @property
    def virtual_sensors(self) -> list[dict[str, Any]]:
        """Return channel attributes which will serve as the basis for virtual sensors.
        Platforms should implement this property and return additional sensors if needed"""
        return []


class ExtaLifeController(ExtaLifeEntity):
    """Base class of a ExtaLife Channel (an equivalent of HA's Entity)."""

    def __init__(self, config_entry: ConfigEntry, serial_no: int):
        super().__init__(config_entry, {"id": 0, "type": int(ExtaLifeDeviceModel.EFC01), "serial": serial_no})

        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_translation_key = "controller"

    async def async_added_to_hass(self) -> None:
        """When entity added to HA"""
        await super().async_added_to_hass()

        # let the Core know about the controller entity
        self._core.controller_entity_added_to_hass(self)

    def _get_unique_id(self) -> str:
        super_id = super()._get_unique_id()
        return f"{super_id}-conn"
        # return self.mac

    @staticmethod
    async def register_controller(config_entry: ConfigEntry, serial_no: int) -> None:
        """Create Controller entity and create device for it in Dev. Registry
        :param config_entry: Config entry
        :param serial_no: Serial number
        :type config_entry: ConfigEntry
        :type serial_no: int
        :return: None
        """

        core: Core = Core.get(config_entry.entry_id)

        platform = entity_platform.EntityPlatform(
            hass=core.get_hass(),
            logger=_LOGGER,
            platform_name=DOMAIN,
            domain=DOMAIN,
            platform=None,
            entity_namespace=None,
            scan_interval=DEFAULT_SCAN_INTERVAL
        )
        platform.config_entry = core.config_entry

        async def async_load_entities() -> None:
            exta_life_controller = ExtaLifeController(config_entry, serial_no)
            await platform.async_add_entities([exta_life_controller])
            return

        await core.platform_register(DOMAIN, async_load_entities)

    async def unregister_controller(self) -> None:
        if self.platform:
            await self.platform.async_remove_entity(self.entity_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # for lost api connection this should return False, so entity status changes to 'unavailable'
        return self.controller is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Register controller in Device Registry"""

        device_info = super().device_info
        device_info.setdefault("connections", {(dr.CONNECTION_NETWORK_MAC, self.mac)})
        device_info.update({"sw_version": self.controller.version_installed})

        return device_info

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""

        es_attr = self._mapping_to_dict(super().extra_state_attributes)
        es_attr.update(
            {
                "name": self.controller.name,
                "type": "gateway",
                "mac_address": self.controller.mac,
                "hostname": ExtaLifeConnParams.get_addr(self.controller.host, self.controller.port),
                "username": self.controller.username,
                "ipv4_address": self.controller.network["ip_address"],
                "ipv4_netmask": self.controller.network["netmask"],
                "ipv4_gateway": self.controller.network["gateway"],
                "ipv4_dns": self.controller.network["dns"],
                "software_version": self.controller.version_installed,
                "ver_check_last": self.controller.ver_check_last,
                "ver_check_next": self.controller.ver_check_next,
            }
        )
        return es_attr

    @property
    def name(self) -> str | None:
        """Return name of the entity"""
        return self.controller.name

    @property
    def mac(self) -> str | None:
        """controller's MAC address"""
        return self.controller.mac

    @property
    def state(self) -> str:
        """Return the controller state. it will be either 'ready' or 'unavailable'"""
        return "connected" if self.controller.is_connected else "disconnected"
