"""Support for ExtaLife devices."""
import datetime
import logging
import voluptuous as vol

from datetime import timedelta
from typing import (
    Any,
    Callable,
    Mapping,
)

import homeassistant.helpers.config_validation as cv

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import Entity
from homeassistant.helpers import entity_platform
from homeassistant.helpers import (
 device_registry as dr,
)
from homeassistant.helpers.entity_component import DEFAULT_SCAN_INTERVAL
from homeassistant.helpers.device_registry import DeviceInfo

from homeassistant.helpers.typing import ConfigType
from homeassistant.core import HomeAssistant
from homeassistant.components.switch import DOMAIN as DOMAIN_SWITCH
from homeassistant.components.light import DOMAIN as DOMAIN_LIGHT
from homeassistant.components.binary_sensor import DOMAIN as DOMAIN_BINARY_SENSOR
from homeassistant.components.climate import DOMAIN as DOMAIN_CLIMATE
from homeassistant.components.cover import DOMAIN as DOMAIN_COVER
from homeassistant.components.sensor import DOMAIN as DOMAIN_SENSOR
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry

from .pyextalife import (
    ExtaLifeAPI,
    ExtaLifeDeviceModel,
    ExtaLifeDeviceModelName,
    ExtaLifeDeviceInfo,
    TCPConnError,
    DEVICE_ARR_ALL_SWITCH,
    DEVICE_ARR_ALL_LIGHT,
    DEVICE_ARR_ALL_COVER,
    DEVICE_ARR_ALL_SENSOR,
    DEVICE_ARR_ALL_CLIMATE,
    DEVICE_ARR_ALL_SENSOR_MEAS,
    DEVICE_ARR_ALL_SENSOR_BINARY,
    DEVICE_ARR_ALL_SENSOR_MULTI,
    DEVICE_ARR_ALL_TRANSMITTER,
    DEVICE_ARR_EXTA_FREE_RECEIVER,
    DEVICE_ICON_ARR_LIGHT,
    DEVICE_ARR_ALL_IGNORE,
    PRODUCT_MANUFACTURER,
    PRODUCT_SERIES,
    PRODUCT_SERIES_EXTA_FREE,
    PRODUCT_CONTROLLER_MODEL,
)
from .helpers.const import (
    DOMAIN,
    CONF_CONTROLLER_IP,
    CONF_USER,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    OPTIONS_COVER_INVERTED_CONTROL,
    SIGNAL_DATA_UPDATED,
    SIGNAL_NOTIF_STATE_UPDATED,
    DOMAIN_TRANSMITTER,
    CONF_OPTIONS,
    OPTIONS_SWITCH,
    OPTIONS_LIGHT,
    OPTIONS_LIGHT_ICONS_LIST,
    OPTIONS_COVER,
    OPTIONS_COVER_INV_CONTROL,
    OPTIONS_GENERAL,
    OPTIONS_GENERAL_POLL_INTERVAL,
    OPTIONS_GENERAL_DISABLE_NOT_RESPONDING,
    VIRTUAL_SENSOR_CHN_FIELD,
    VIRTUAL_SENSOR_DEV_CLS,
    VIRTUAL_SENSOR_PATH,
    VIRTUAL_SENSOR_ALLOWED_CHANNELS
)

from .helpers.core import Core
from .helpers.services import ExtaLifeServices
from .config_flow import get_default_options

_LOGGER = logging.getLogger(__name__)

OPTIONS_DEFAULTS = get_default_options()

# schema validations
OPTIONS_CONF_SCHEMA = {
    vol.Optional(OPTIONS_GENERAL, default=OPTIONS_DEFAULTS[OPTIONS_GENERAL]): {
        vol.Optional(
            OPTIONS_GENERAL_POLL_INTERVAL,
            default=OPTIONS_DEFAULTS[OPTIONS_GENERAL][OPTIONS_GENERAL_POLL_INTERVAL],
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
            OPTIONS_COVER_INV_CONTROL,
            default=OPTIONS_DEFAULTS[OPTIONS_COVER][OPTIONS_COVER_INVERTED_CONTROL],
        ): cv.boolean,
    },
}

# configuration.yaml config schema for HA validations
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_CONTROLLER_IP, default=""): cv.string,
                vol.Required(CONF_USER): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(
                    CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                ): cv.positive_int,
                vol.Optional(
                    CONF_OPTIONS, default=get_default_options()
                ): OPTIONS_CONF_SCHEMA,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


# noinspection PyUnusedLocal
async def async_migrate_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    #  Flatten configuration but keep old data if user rollbacks HASS
    if config_entry.version == 1:

        options = {**config_entry.options}
        options.setdefault(
            OPTIONS_GENERAL,
            {
                OPTIONS_GENERAL_POLL_INTERVAL: config_entry.data.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                )
            },
        )
        config_entry.options = {**options}

        new = {**config_entry.data}
        try:
            new.pop(CONF_POLL_INTERVAL)
            # get rid of erroneously migrated options from integration 1.0
            new.pop(CONF_OPTIONS)
        except KeyError:     # pylint: disable=bare-except
            pass
        config_entry.data = {**new}

        config_entry.version = 2

    _LOGGER.info("Migration to version %s successful", config_entry.version)

    return True


# noinspection PyUnusedLocal
async def async_setup(
        hass: HomeAssistant,
        hass_config: ConfigType) -> bool:
    """Set up Exta Life component from configuration.yaml. This will basically
    forward the config to a Config Flow and will migrate to Config Entry"""

    _LOGGER.debug("hass_config: %s", hass_config)

    if not hass.config_entries.async_entries(DOMAIN) and DOMAIN in hass_config:

        hass.data.setdefault(
            DOMAIN, {CONF_OPTIONS: hass_config[DOMAIN].get(CONF_OPTIONS, None)}
        )
        _LOGGER.debug("async_setup, hass.data.domain: %s", hass.data.get(DOMAIN))

        result = hass.async_create_task(                            # pylint: disable=unused-variable
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data=hass_config[DOMAIN]
            )
        )

    return True


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Set up Exta Life component from a Config Entry"""

    _LOGGER.debug("async_setup_entry(): starting for %s", config_entry.entry_id)

    hass.data.setdefault(DOMAIN, {})
    Core.create(hass, config_entry)
    result = await initialize(hass, config_entry)

    _LOGGER.debug("async_setup_entry(): finished for %s", config_entry.entry_id)

    return result


# noinspection PyUnusedLocal
async def async_unload_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry) -> bool:
    """Unload a config entry: unload platform entities, stored data, deregister signal listeners"""

    _LOGGER.debug("async_unload_entry(): starting for %s", config_entry.entry_id)

    core = Core.get(config_entry.entry_id)
    result = await core.unload_entry_from_hass()

    _LOGGER.debug("async_unload_entry(): finished for %s", config_entry.entry_id)

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

            _LOGGER.debug("init_options, yaml_options %s", yaml_options)

            options = default if yaml_options is None else yaml_options

        # set default values if something is missing
        options_def = options.copy()
        for k, v in default.items():
            options_def.setdefault(k, v)

        # check for changes and if options should be persisted
        if options_def != options or not config_entry.options:
            hass.config_entries.async_update_entry(config_entry, options=options_def)

    async def api_connect(conn_user: str, conn_password: str, conn_host: str | None) -> ExtaLifeAPI:
        el_controller = Core.get(config_entry.entry_id).api
        await el_controller.async_connect(conn_user, conn_password, host=conn_host)
        return el_controller

    init_options()

    controller = None

    el_conf = config_entry.data
    core = Core.get(config_entry.entry_id)

    data_manager: ChannelDataManager = core.data_manager

    controller_ip: str = el_conf[CONF_CONTROLLER_IP]  # will be known after config flow

    try:
        _LOGGER.info("ExtaLife initializing... [Debugger attached: %s]",
                     "YES" if ExtaLifeAPI.is_debugger_active() else "NO")

        if controller_ip is not None:
            _LOGGER.debug("Trying to connect to controller using IP: %s", controller_ip)
        else:
            _LOGGER.info("No controller IP specified. Trying autodiscovery")

        # get instance: this will already try to connect and logon
        try:
            controller = await api_connect(
                el_conf[CONF_USER], el_conf[CONF_PASSWORD], controller_ip
            )
        except TCPConnError as e:           # pylint: disable=invalid-name
            _LOGGER.debug(
                "Connection exception: %s, class: %s", e.previous, e.previous.__class__
            )
            # invalid IP / IP changed? - try auto-detection
            if isinstance(e.previous, OSError) and e.previous.errno == 113:
                _LOGGER.warning(
                    "Could not connect to EFC-01 on IP stored in configuration: %s. "
                    "Trying to discover controller IP in the network",
                    controller_ip,
                )
                # controller = await hass.async_add_executor_job(api_connect, el_conf[CONF_USER],
                # el_conf[CONF_PASSWORD], None)
                controller = await api_connect(
                    el_conf[CONF_USER], el_conf[CONF_PASSWORD], None
                )

                # update ConfigEntry with new IP
                cur_data = {**config_entry.data}
                cur_data.update({CONF_CONTROLLER_IP: controller.host})
                hass.config_entries.async_update_entry(config_entry, data=cur_data)
                _LOGGER.info("Controller IP updated to: %s", controller.host)
            else:
                raise e
        _LOGGER.info("Connected to controller on IP: %s", controller.host)

        sw_version = controller.sw_version

        if sw_version is not None:
            _LOGGER.info("EFC-01 Software version: %s", sw_version)
        else:
            _LOGGER.error(
                "Error communicating with the EFC-01 controller. Return data %s",
                sw_version,
            )
            return False

    except TCPConnError as err:
        host = controller.host if (controller and controller.host) else "unknown"
        _LOGGER.error("Could not connect to EFC-01 on IP: %s", host)

        await core.unload_entry_from_hass()
        raise ConfigEntryNotReady from err

    await core.register_controller()

    await data_manager.async_execute_status_polling(True)

    # publish services to HA service registry
    await core.async_register_services()

    _LOGGER.info("Exta Life integration setup successfully!")
    return True


class ChannelDataManager:
    """Get the latest data from EFC-01, call device discovery, handle status notifications."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the data object."""
        self.data = None
        self._hass: HomeAssistant = hass
        self._config_entry: ConfigEntry = config_entry
        self._listeners = []

        self.channels_indx = {}
        self.initial_channels = {}

        self._poller_callback_remove: Callable[[], None] | None = None

    @property
    def core(self) -> Core:
        return Core.get(self._config_entry.entry_id)

    @property
    def controller(self) -> ExtaLifeAPI:
        return Core.get(self._config_entry.entry_id).api

    # callback
    # TODO: APIResponse not dict[str, Any]
    def on_notify(self, message: dict[str, Any]):
        _LOGGER.debug("Received status change notification from controller: %s", message)
        data = message.get("data")
        channel = data.get("channel", "#")
        channel_id = str(data.get("id")) + "-" + str(channel)

        # inform HA entity of state change via notification
        signal = ExtaLifeChannel.get_notif_upd_signal(channel_id)
        if channel != "#":
            self.core.async_signal_send(signal, data)
        else:
            self.core.async_signal_send_sync(signal, data)

    def update_channel(self, channel_id: str, channel_data: dict[str, Any]) -> None:
        """Update data of a channel e.g. after notification data received and processed
        by an entity"""

        self.channels_indx.update({channel_id: channel_data})

    async def async_execute_status_polling(self, poll_now: bool = True) -> None:
        """Executes status polling triggered externally, not via periodic callback + resets next poll time"""

        if self._poller_callback_remove is not None:
            self._poller_callback_remove()
        self._poller_callback_remove = None

        if poll_now:
            await self._async_update_callback()

        self.setup_periodic_callback()

    async def async_stop_polling(self) -> None:
        """Turn off periodic callbacks for status update"""

        if self._poller_callback_remove is not None:
            self._poller_callback_remove()
        self._poller_callback_remove = None

    async def _async_update_callback(self, now: datetime = None) -> None:
        """Get the latest device&channel status data from EFC-01.
        This method is called from HA task scheduler via async_track_time_interval"""

        _LOGGER.debug("Executing EFC-01 status polling")
        # use Exta Life TCP communication class

        # if connection error or other - will receive None
        # otherwise it contains a list of channels
        channels = await self.controller.async_get_channels()

        if channels is None:
            _LOGGER.warning("No Channels could be obtained from the controller")
            return

        # create indexed access: dict from list element
        # dict key = "data" section
        for elem in channels:
            self.update_channel(elem["id"], elem["data"])

        self.core.async_signal_send(SIGNAL_DATA_UPDATED)

        _LOGGER.debug(
            "Exta Life: status for %d devices updated", len(self.channels_indx)
        )

        await self.async_discover_devices()

        if now is None:
            # store initial channel list for subsequent discovery runs for detection of new devices
            # store only for the 1st call (by setup code, not by HA)
            self.initial_channels = self.channels_indx.copy()

    def setup_periodic_callback(self) -> None:
        """(Re)set periodic callback period based on options"""

        # register callback for periodic status update polling + device discovery
        interval = self._config_entry.options.get(OPTIONS_GENERAL).get(
            OPTIONS_GENERAL_POLL_INTERVAL
        )

        _LOGGER.debug("setup_periodic_callback(). Setting interval: %s", interval)

        self._poller_callback_remove = self.core.async_track_time_interval(
            self._async_update_callback, timedelta(minutes=interval)
        )

    async def async_discover_devices(self) -> None:
        """
        Fetch / refresh device data & discover devices and register them in Home Assistant.
        """

        component_configs: dict = {}
        other_configs = {}

        # get data from the ChannelDataManager object stored in HA object data

        entities = 0
        for channel_id, channel_data in self.channels_indx.items():  # -> dict id:data

            # do discovery only for newly discovered devices
            if self.initial_channels.get(channel_id):
                continue

            channel = {"id": channel_id, "data": channel_data}
            device_type = channel_data.get("type")
            component_name = None

            # skip some devices that are not to be shown nor controlled by HA
            if device_type in DEVICE_ARR_ALL_IGNORE:
                continue

            if device_type in DEVICE_ARR_ALL_SWITCH:
                icon = channel["data"]["icon"]
                if icon in self._config_entry.options.get(DOMAIN_LIGHT).get(
                    OPTIONS_LIGHT_ICONS_LIST
                ):
                    component_name = DOMAIN_LIGHT
                else:
                    component_name = DOMAIN_SWITCH

            elif device_type in DEVICE_ARR_ALL_LIGHT:
                component_name = DOMAIN_LIGHT

            elif device_type in DEVICE_ARR_ALL_COVER:
                component_name = DOMAIN_COVER

            elif device_type in DEVICE_ARR_ALL_SENSOR_MEAS:
                component_name = DOMAIN_SENSOR

            elif device_type in DEVICE_ARR_ALL_SENSOR_BINARY:
                component_name = DOMAIN_BINARY_SENSOR

            elif device_type in DEVICE_ARR_ALL_SENSOR_MULTI:
                component_name = DOMAIN_SENSOR

            elif device_type in DEVICE_ARR_ALL_CLIMATE:
                component_name = DOMAIN_CLIMATE

            elif device_type in DEVICE_ARR_ALL_TRANSMITTER:
                other_configs.setdefault(DOMAIN_TRANSMITTER, []).append(channel)
                continue

            if component_name is None:
                _LOGGER.warning(
                    "Unsupported device type: %s, channel id: %s",
                    device_type,
                    channel["id"],
                )
                continue

            component_configs.setdefault(component_name, []).append(channel)
            entities += 1

        _LOGGER.debug("Exta Life devices found during discovery: %d", entities)

        # Load discovered devices

        if component_configs:
            # can happen we don't have any sensors, so we need to put an empty list to trigger
            # creation of virtual sensors (if any) for
            component_configs.setdefault(DOMAIN_SENSOR, [])

            # sensors must be last as platforms will delegate their attributes to virtual sensors
            component_configs[DOMAIN_SENSOR] = component_configs.pop(DOMAIN_SENSOR)

            for component_name, channels in component_configs.items():
                # store array of channels (variable 'channels') for each platform
                self.core.push_channels(component_name, channels)

                # 'sync' call to synchronize channels' stack with platform setup
                await self._hass.config_entries.async_forward_entry_setup(
                    self._config_entry, component_name
                )
                # self._hass.async_create_task(
                #     self._hass.config_entries.async_forward_entry_setup(
                #         self._config_entry, component_name
                #     )
                # )

        # setup pseudo-platforms
        for component_name, channels in other_configs.items():
            # store array of channels (variable 'channels') for each platform
            self.core.push_channels(component_name, channels, True)
            self._hass.async_create_task(
                self.core.async_setup_custom_platform(component_name)
            )


class ExtaLifeChannel(Entity):
    """Base class of a ExtaLife Channel (an equivalent of HA's Entity).
    ParentEntity - instance of Parent Entity which instantiates this entity
    add_entity_cb - HA callback for adding entity in entity registry
    """

    def __init__(self, channel_data: dict[str, Any], config_entry: ConfigEntry):
        """Channel data -- channel information from PyExtaLife."""

        self._assumed_on: bool = False
        self.config_entry: ConfigEntry = config_entry
        self.channel_id: str = channel_data.get("id")
        self.channel_data: dict[str, Any] = channel_data.get("data")
        self.data_available: bool = True

    @staticmethod
    def _mapping_to_dict(mapping: Mapping[str, Any] | None) -> dict[str, Any]:
        return dict(mapping) if mapping is not None else {}

    @staticmethod
    def _extra_state_attribute_update(src: dict[str, Any], dst: dict[str, Any], key: str):
        if src.get(key) is not None:
            dst.update({key: src.get(key)})

    @staticmethod
    def get_notif_upd_signal(ch_id: str) -> str:
        return f"{SIGNAL_NOTIF_STATE_UPDATED}_{ch_id}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        _LOGGER.debug("async_added_to_hass() for entity: %s", self.entity_id)
        Core.get(self.config_entry.entry_id).async_signal_register(
            SIGNAL_DATA_UPDATED, self.async_update_callback
        )

        Core.get(self.config_entry.entry_id).async_signal_register(
            self.get_notif_upd_signal(self.channel_id),
            self.async_state_notif_update_callback,
        )

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()

    async def async_update_callback(self) -> None:
        """Inform HA of state update from status poller"""
        _LOGGER.debug("Update callback for entity id: %s", self.entity_id)
        self.async_schedule_update_ha_state(True)

    async def async_state_notif_update_callback(self, *args: Any) -> None:
        """Inform HA of state change received from controller status notification"""
        data = args[0]
        _LOGGER.debug(
            "State update notification callback for entity id: %s, data: %s",
            self.entity_id,
            data,
        )

        self.on_state_notification(data)

    def on_state_notification(self, data: dict[str, Any]) -> None:
        """must be overridden in entity subclasses"""

    def get_unique_id(self) -> str:
        """Provide unique id for HA entity registry"""
        return f"extalife-{str(self.channel_data.get('serial'))}-{self.channel_id}"

    @property
    def should_poll(self) -> bool:
        """
        Turn off HA polling in favour of update-when-needed status changes.
        Updates will be passed to HA by calling async_schedule_update_ha_state() for each entity
        """
        return False

    @property
    def core(self) -> Core:
        return Core.get(self.config_entry.entry_id)

    @property
    def controller(self) -> ExtaLifeAPI:
        """Return PyExtaLife's controller component associated with entity."""
        return self.core.api

    @property
    def data_poller(self) -> ChannelDataManager:
        """Return Data poller object"""
        return self.core.data_manager

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self.get_unique_id()

    @property
    def device_type(self) -> ExtaLifeDeviceModel:
        """Return device type"""
        return ExtaLifeDeviceModel(self.channel_data.get("type"))

    @property
    def model(self) -> ExtaLifeDeviceModelName:
        """Return model"""
        return ExtaLifeDeviceInfo.get_model_name(self.device_type)

    @property
    def is_exta_free(self) -> bool:
        """Returns boolean if entity represents Exta Free device"""
        exta_free_device = self.channel_data.get("exta_free_device")
        if exta_free_device is None or not bool(exta_free_device):
            return False
        return True

    @property
    def assumed_state(self) -> bool:
        """Returns boolean if entity status is assumed status"""
        ret = self.is_exta_free
        _LOGGER.debug("Assumed state for entity: %s, %s", self.entity_id, ret)
        return ret

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device specific attributes."""

        prod_series = (
            PRODUCT_SERIES if not self.is_exta_free else PRODUCT_SERIES_EXTA_FREE
        )
        return {
            "identifiers": {(DOMAIN, self.channel_data.get("serial"))},
            "name": f"{PRODUCT_MANUFACTURER} {prod_series} {self.model}",
            "manufacturer": PRODUCT_MANUFACTURER,
            "model": self.model,
            "via_device": (DOMAIN, self.controller.mac),
        }

    @property
    def name(self) -> str | None:
        """Return name of the entity"""
        return self.channel_data["alias"]

    async def async_action(self, action, **add_pars: Any) -> list | None:
        """
        Run controller command/action.

        Actions are currently hardcoded in platforms
        """
        _LOGGER.debug(
            "Executing action %s on channel %s, params: %s",
            action,
            self.channel_id,
            add_pars,
        )

        try:
            resp = await self.controller.async_execute_action(action, self.channel_id, **add_pars)
        except TCPConnError as err:
            _LOGGER.error(err.data)
            return None

        return resp

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        is_timeout = (
            self.channel_data.get("is_timeout")
            if self.config_entry.options.get(OPTIONS_GENERAL_DISABLE_NOT_RESPONDING)
            else False
        )
        _LOGGER.debug(
            "available() for entity: %s. self.data_available: %s; 'is_timeout': %s",
            self.entity_id,
            self.data_available,
            is_timeout,
        )

        return self.data_available is True and is_timeout is False

    async def async_update(self) -> None:
        """Call to update state."""
        # data poller object contains PyExtaLife API channel data dict value pair: {("id"): ("data")}
        channel_indx = self.data_poller.channels_indx

        # read "data" section/dict by channel id
        data = channel_indx.get(self.channel_id)

        _LOGGER.debug(
            "async_update() for entity: %s, data to be updated: %s",
            self.entity_id,
            data,
        )

        if data is None:
            self.data_available = False
            return

        self.data_available = True
        self.channel_data = data

    def sync_data_update_ha(self) -> None:
        """Performs update of Data Manager data with Entity data and calls HA state update.
        This is useful e.g. when Entity receives notification update, processes it and
        then must update its state. For consistency reasons - Data Manager is updated and then
        HA status update is scheduled"""

        self.data_poller.update_channel(self.channel_id, self.channel_data)
        self.async_schedule_update_ha_state(True)

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
    def virtual_sensors(self) -> list[dict[str, Any]]:
        """Return channel attributes which will serve as the basis for virtual sensors.
        Platforms should implement this property and return additional sensors if needed"""
        return []

    def _get_virtual_sensors(self) -> list[dict[str, Any]]:
        """By default, check all entity attributes and return virtual sensor config"""
        from .sensor import MAP_EXTA_ATTRIBUTE_TO_DEV_CLASS

        attr: list[dict[str, Any]] = []
        for k, v in self.channel_data.items():                      # pylint: disable=unused-variable
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

    def is_virtual_sensor_allowed(self, attr_name: str) -> bool:
        """Check if virtual sensor should be created for an attribute based on settings"""
        from .sensor import VIRTUAL_SENSOR_RESTRICTIONS

        channel = self.channel_data.get("channel")
        restr = VIRTUAL_SENSOR_RESTRICTIONS.get(attr_name)

        if restr:
            if not (channel in restr.get(VIRTUAL_SENSOR_ALLOWED_CHANNELS)):
                return False

        return True

    # TODO: [typing] Need more specific dict
    def push_virtual_sensor_channels(self, virtual_sensor_domain: str, channel_data: dict):
        """Push additional, virtual sensor channels for entity attributes. These should be
        processed by all platforms during platform setup and ultimately sensor entities
        shouldbe created by the sensor platform"""

        virtual_sensors = self._get_virtual_sensors()
        _LOGGER.debug("Virtual sensors: %s", virtual_sensors)
        for virtual in virtual_sensors:
            v_channel_data = channel_data.copy()
            v_channel_data.update({VIRTUAL_SENSOR_CHN_FIELD: virtual})
            self.core.push_channels(virtual_sensor_domain, [v_channel_data], append=True, custom=True)

    @staticmethod
    def format_state_attr(attr: dict[str, Any]) -> dict[str, Any]:
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


class ExtaLifeController(Entity):
    """Base class of a ExtaLife Channel (an equivalent of HA's Entity)."""

    def __init__(self, entry_id: str):
        self._entry_id: str = entry_id
        self._core: Core = Core.get(entry_id)

    @staticmethod
    def _mapping_to_dict(mapping: Mapping[str, Any] | None) -> dict[str, any]:
        return dict(mapping) if mapping is not None else {}

    @staticmethod
    async def register_controller(entry_id: str) -> None:
        """Create Controller entity and create device for it in Dev. Registry
        entry_id - Config Entry entry_id"""

        core: Core = Core.get(entry_id)

        platform = entity_platform.EntityPlatform(
            hass=core.get_hass(),
            logger=_LOGGER,
            platform_name=DOMAIN,
            domain=DOMAIN,
            platform=None,
            entity_namespace=None,
            scan_interval=DEFAULT_SCAN_INTERVAL,
        )
        platform.config_entry = core.config_entry

        exta_life_controller = ExtaLifeController(core.config_entry.entry_id)
        await platform.async_add_entities([exta_life_controller])

    async def unregister_controller(self) -> None:
        if self.platform:
            await self.platform.async_remove_entity(self.entity_id)

    async def async_added_to_hass(self) -> None:
        """When entity added to HA"""

        # let the Core know about the controller entity
        self._core.controller_entity_added_to_hass(self)

    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self.mac

    @property
    def mac(self) -> str | None:
        """controller's MAC address"""
        return self.api.mac

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend, if any."""
        return "mdi:cube-outline"

    @property
    def should_poll(self) -> bool:
        """Turn off HA status polling"""
        return False

    @property
    def core(self) -> Core:
        return self._core

    @property
    def api(self) -> ExtaLifeAPI:
        """Return PyExtaLife's controller API instance."""
        return self.core.api

    @property
    def device_info(self) -> DeviceInfo | None:
        """Register controller in Device Registry"""
        return {
            "connections": {(dr.CONNECTION_NETWORK_MAC, self.mac)},
            "identifiers": {(DOMAIN, self.mac)},
            "manufacturer": PRODUCT_MANUFACTURER,
            "name": f"{PRODUCT_MANUFACTURER} {PRODUCT_SERIES} {PRODUCT_CONTROLLER_MODEL}",
            "model": PRODUCT_CONTROLLER_MODEL,
            "sw_version": self.api.sw_version
        }

    @property
    def name(self) -> str | None:
        """Return name of the entity"""
        return self.api.name

    @property
    def config_entry(self) -> ConfigEntry:
        return self.core.config_entry

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # for lost api connection this should return False, so entity status changes to 'unavailable'
        return self.api.is_connected

    @property
    def state(self) -> str:
        """Return the controller state. it will be either 'ready' or 'unavailable'"""
        return "ready"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        es_attr = self._mapping_to_dict(super().extra_state_attributes)
        es_attr.update(
                {
                     "type": "gateway",
                     "mac_address": self.mac,
                     "ipv4_address:": self.api.host,
                     "software_version": self.api.sw_version,
                     "name": self.api.name,
                }
            )
        return es_attr

    async def async_update(self) -> None:
        """Entity update callback"""
        # not necessary for the controller entity; will be updated on demand, externally
