import asyncio
import logging
import importlib
import datetime
from typing import Callable, Any
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from .const import DATA_CORE, DOMAIN, CONF_EXTALIFE_EVENT_SCENE
from ..pyextalife import ExtaLifeAPI
from .typing import (
    ChannelDataManagerType,
    CoreType,
    DeviceManagerType
)
from .services import ExtaLifeServices


MAP_NOTIF_CMD_TO_EVENT = {
    ExtaLifeAPI.CMD_ACTIVATE_SCENE: CONF_EXTALIFE_EVENT_SCENE
}


_LOGGER = logging.getLogger(__name__)


# noinspection PyUnusedLocal
async def options_change_callback(hass: HomeAssistant, config_entry: ConfigEntry):
    """Options update listener"""

    core = Core.get(config_entry.entry_id)
    core.data_manager.setup_periodic_callback()


def import_executor_callback(module: str, func: str) -> Callable[[HomeAssistant, ConfigEntry], None] | None:

    result = None
    package = ".".join(__package__.split(".")[:-1])  # 1 level above current package
    try:
        _LOGGER.debug("_import_executor_callback(), module: %s, from: %s", module, package)
        imp_module = importlib.import_module("." + module, package)

        _LOGGER.debug("_import_executor_callback(), func: %s", func)
        result = getattr(imp_module, func)
    except Exception as err:
        _LOGGER.warning("async_setup_custom_platforms(), failed to import module %s from package %s, %s",
                        module, package, repr(err))
    return result


class Core:

    _inst: dict[str, CoreType] = dict()
    _hass: HomeAssistant = None
    _services: ExtaLifeServices = None

    _is_stopping = False

    @classmethod
    def create(cls, hass: HomeAssistant, config_entry: ConfigEntry):
        """Create Core instance for a given Config Entry"""
        cls._hass = hass
        inst = Core(config_entry)

        hass.data[DOMAIN][DATA_CORE] = cls._inst

        # register callback for HomeAssistant Stop event
        cls._hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, cls._on_homeassistant_stop
        )
        return inst

    @classmethod
    def get(cls, entry_id: str) -> CoreType:  # forward
        """Get instance of the Core object based on Config Entry ID"""
        return cls._inst.get(entry_id)

    @classmethod
    def get_hass(cls) -> HomeAssistant:
        """Return HomeAssistant instance"""
        return cls._hass

    def __init__(self, config_entry: ConfigEntry):
        """initialize instance"""
        from .device import DeviceManager
        from ..transmitter import TransmitterManager
        from .. import ChannelDataManager

        self._inst[config_entry.entry_id] = self

        self._config_entry = config_entry
        self._dev_manager = DeviceManager(config_entry, self)
        self._transmitter_manager = TransmitterManager(config_entry)
        self._api = ExtaLifeAPI(
            self.hass.loop,
            on_connect_callback=self._on_reconnect_callback,
            on_disconnect_callback=self._on_disconnect_callback,
        )
        self._signal_callbacks = []
        self._track_time_callbacks = []
        self._platforms = dict()
        self._platforms_cust = dict()
        self._data_manager = ChannelDataManager(self.hass, self.config_entry)
        self._api.set_notification_callback(self._on_status_notification_callback)
        self._queue = asyncio.Queue()
        self._queue_task = Core.get_hass().loop.create_task(self._queue_worker())
        self._signals = {}

        self._periodic_reconnect_remove_callback = None

        self._options_change_remove_callback = config_entry.add_update_listener(
            options_change_callback
        )

        self._controller_entity: Entity | None = None

        self._storage = {}

        self._is_unloading = False

    async def unload_entry_from_hass(self):
        """Called when ConfigEntry is unloaded from Home Assistant"""
        self._is_unloading = True

        await Core._callbacks_cleanup(self.config_entry.entry_id)
        await self.data_manager.async_stop_polling()

        await self.api.disconnect()

        # unload services when the last entry is unloaded
        if len(self._inst) == 1 and self._services:
            await self._services.async_unregister_services()

        for platform in self._platforms:
            await self.hass.config_entries.async_forward_entry_unload(
                self.config_entry, platform
            )

        await self.async_unload_custom_platforms()

        # remove instance only after everything is unloaded
        self._inst.pop(self.config_entry.entry_id)

    # noinspection PyUnusedLocal
    @classmethod
    async def _on_homeassistant_stop(cls, event):
        """Called when Home Assistant is shutting down"""
        cls._is_stopping = True

        await cls._callbacks_cleanup()
        for inst in cls._inst.values():
            await Core._callbacks_cleanup(inst.config_entry.entry_id)
            await inst.data_manager.async_stop_polling()

            await inst.api.disconnect()

    @classmethod
    async def _callbacks_cleanup(cls, entry_id=None):
        """Cleanup signal callbacks and callback-handling asyncio queues"""
        instances = (
            [cls.get(entry_id)]
            if entry_id
            else [inst_obj for inst_id, inst_obj in cls._inst.items()]
        )
        for inst in instances:
            inst._queue.put_nowait(None)  # terminate callback worker
            inst.unregister_signal_callbacks()
            inst.unregister_track_time_callbacks()

            if inst._periodic_reconnect_remove_callback:
                try:
                    inst._periodic_reconnect_remove_callback()
                except ValueError:
                    pass

            if inst._options_change_remove_callback:
                try:
                    inst._options_change_remove_callback()
                except ValueError:
                    pass

            inst._queue_task.cancel()
            try:
                await inst._queue_task
            except asyncio.CancelledError:
                pass

    async def async_register_services(self):
        """ " Register services, but only once"""
        if self._services is None:
            self._services = ExtaLifeServices(self._hass)
            await self._services.async_register_services()

    def _on_reconnect_callback(self):
        """Execute actions on (re)connection to controller"""

        if self._periodic_reconnect_remove_callback is not None:
            self._periodic_reconnect_remove_callback()

        # Update controller software info
        if self._controller_entity is not None:
            self._controller_entity.schedule_update_ha_state()

    def _on_disconnect_callback(self):
        """Execute actions on disconnection with controller"""

        if self._is_unloading or self._is_stopping:
            return

        # Update controller software info
        if self._controller_entity is not None:
            self._controller_entity.schedule_update_ha_state()

        # need to schedule periodic reconnection attempt
        if self._periodic_reconnect_remove_callback is not None:
            self._periodic_reconnect_remove_callback()
        self._periodic_reconnect_remove_callback = self.async_track_time_interval(
            self._periodic_reconnect_callback, datetime.timedelta(seconds=30)
        )

    def _on_status_notification_callback(self, msg):
        if self._is_unloading or self._is_stopping:
            return

        # forward only state notifications to data manager to update channels
        if msg.get("command") == self.api.CMD_CONTROL_DEVICE:
            self._data_manager.on_notify(msg)

        self._put_notification_on_event_bus(msg)

    # noinspection PyUnusedLocal
    async def _periodic_reconnect_callback(self, now):
        """Reconnect with the controller after connection is lost
        This will be executed periodically until reconnection is successful"""
        await self.api.async_reconnect()

    async def register_controller(self):
        """Register controller in Device Registry and create its entity"""
        from .. import ExtaLifeController

        await ExtaLifeController.register_controller(self.config_entry.entry_id)

    def controller_entity_added_to_hass(self, entity):
        """Callback called by controller entity when the entity is added to HA

        entity - Entity object"""
        self._controller_entity = entity

    def _put_notification_on_event_bus(self, msg):
        """ This method raises a notification on HA Event Bus """
        data = msg.get("data")
        event = MAP_NOTIF_CMD_TO_EVENT.get(msg.get("command"))
        if event:
            self._hass.bus.async_fire(event, event_data=data)

    @property
    def api(self) -> ExtaLifeAPI:
        return self._api

    @property
    def data_manager(self) -> ChannelDataManagerType:
        return self._data_manager

    @property
    def config_entry(self):
        return self._config_entry

    @property
    def hass(self) -> HomeAssistant:
        return Core._hass

    @property
    def dev_manager(self) -> DeviceManagerType:
        return self._dev_manager

    @property
    def signal_remove_callbacks(self):
        return self._signal_callbacks

    def add_signal_remove_callback(self, callback, cb_type: str):
        self._signal_callbacks[cb_type] = callback

    def unregister_signal_callbacks(self):
        for callback in self.signal_remove_callbacks:
            callback()

    def unregister_track_time_callbacks(self):
        """Call delete callbacks for time interval registered callbacks"""
        for callback in self._track_time_callbacks:
            callback()

        self._track_time_callbacks = list()

    def push_channels(self, platform: str, data: list, custom=False, append=False):
        """Store channel data temporarily for platform setup

        custom - custom, virtual platform"""
        if custom:
            if append:
                self._platforms_cust.setdefault(platform, [])
                self._platforms_cust[platform].append(data)
            else:
                self._platforms_cust[platform] = data
        else:
            if append:
                self._platforms.setdefault(platform, [])
                self._platforms[platform].append(data)
            else:
                self._platforms[platform] = data

    def get_channels(self, platform: str) -> list:
        """Return list of channel data per platform"""
        channels = self._platforms.get(platform)
        if channels is None:
            channels = self._platforms_cust.get(platform)
        return channels

    def pop_channels(self, platform: str):
        """Delete list of channel data per platform"""
        if self._platforms.get(platform) is None:
            self._platforms_cust[platform] = []
        else:
            self._platforms[platform] = []

    async def async_setup_custom_platform(self, platform: str):
        """Setup other, custom (pseudo)platforms"""

        async_setup_entry = await self._hass.async_add_import_executor_job(import_executor_callback,
                                                                           platform, "async_setup_entry")
        if async_setup_entry is not None:
            await async_setup_entry(self.hass, self.config_entry)
            _LOGGER.debug("Custom platform '%s' has been configured")

    async def async_unload_custom_platforms(self):
        """Unload other, custom (pseudo)platforms"""

        for platform, channels in self._platforms_cust.items():

            if platform.startswith("virtual"):
                # virtual platforms does not have import module so cannot be unloaded
                continue

            async_unload_entry = await self._hass.async_add_import_executor_job(import_executor_callback,
                                                                                platform, "async_unload_entry")
            if async_unload_entry is not None:
                await async_unload_entry(self.hass, self.config_entry)

    def storage_add(self, inst_id: str, inst_obj):
        self._storage.update({inst_id: inst_obj})

    def storage_get(self, inst_id: str):
        self._storage.get(inst_id)

    def storage_remove(self, inst_id: str):
        self._storage.pop(inst_id)

    def async_track_time_interval(self, callback, interval: datetime.timedelta):
        """Add a listener that fires repetitively at every timedelta interval."""
        remove_callback = async_track_time_interval(self.hass, callback, interval)
        self._track_time_callbacks.append(remove_callback)

        def _managed_remove_callback():
            i = 0
            for cb in self._track_time_callbacks:
                if cb == remove_callback:
                    remove_callback()
                    self._track_time_callbacks.pop(i)
                    break
                i += 1

        return _managed_remove_callback

    def async_signal_register(self, signal: str, target) -> Callable:
        """Connect a callable function to a signal.

        This method must be run in the event loop.
        """
        signal_ext = str(self._config_entry.entry_id) + signal
        if signal_ext not in self._signals:
            self._signals[signal_ext] = []

        self._signals[signal_ext].append(target)

        _LOGGER.debug(
            "async_signal_register(), signal: %s, signal_ext: %s, target: %s",
            signal,
            signal_ext,
            target,
        )

        def async_remove_signal() -> None:
            """Remove signal listener."""
            _LOGGER.debug(
                "async_remove_signal(), signal: %s, signal_ext: %s, target: %s",
                signal,
                signal_ext,
                target,
            )
            try:
                self._signals[signal_ext].remove(target)
            except (KeyError, ValueError):
                # KeyError is key target listener did not exist
                # ValueError if listener did not exist within signal
                _LOGGER.warning("Unable to remove unknown dispatcher %s", target)

        return async_remove_signal

    def async_signal_send(self, signal: str, *args: Any) -> None:
        """Send signal and data.

        This method must be run in the event loop.
        """
        signal_int = str(self._config_entry.entry_id) + signal
        target_list = self._signals.get(signal_int, [])

        _LOGGER.debug(
            "async_signal_send(), signal: %s, signal_int: %s, target_list: %s, *args: %s",
            signal,
            signal_int,
            target_list,
            args,
        )

        for target in target_list:
            _LOGGER.debug("async_signal_send(), target: %s", target)
            coroutine = target(*args)
            self._hass.async_create_task(coroutine)

    def async_signal_send_sync(self, signal: str, args) -> None:
        """Send signal and data.

        This method must be run in the event loop.
        """
        signal_int = str(self._config_entry.entry_id) + signal
        target_list = self._signals.get(signal_int, [])

        for target in target_list:
            _LOGGER.debug("queue.put %s", target)
            self._queue.put_nowait({"signal": signal_int, "data": args})

    async def _queue_worker(self):
        _LOGGER.debug("_queue_worker started")
        while True:
            msg = await self._queue.get()

            if msg is None:
                break

            _LOGGER.debug("queue.get(): %s", msg)
            signal = msg.get("signal")
            data = msg.get("data")

            for callback in self._signals.get(signal):
                _LOGGER.debug("_queue_worker callback: %s(%s)", callback, data)
                callback(data)

        _LOGGER.debug("_queue_worker done")
