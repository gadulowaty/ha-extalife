""" ExtaLife JSON API wrapper library. Enables device control, discovery and status fetching from EFC-01 controller """
from __future__ import print_function
import asyncio
import json
import logging
import re
import socket
import sys

from asyncio.events import AbstractEventLoop
from datetime import datetime
from enum import (
    IntEnum,
    StrEnum
)
from typing import (
    Awaitable,
    Callable,
    Any
)

_LOGGER = logging.getLogger(__name__)

# controller info
PRODUCT_MANUFACTURER = "ZAMEL"
PRODUCT_SERIES = "Exta Life"
PRODUCT_SERIES_EXTA_FREE = "Exta Free"
PRODUCT_CONTROLLER_MODEL = "EFC-01"


class ExtaLifeDeviceModelName(StrEnum):
    # Exta Life
    RNK22 = "RNK-22"
    RNK22_TEMP_SENSOR = "RNK-22 temperature sensor"
    RNK24 = "RNK-24"
    RNK24_TEMP_SENSOR = "RNK-24 temperature sensor"
    P4572 = "P-457/2"
    P4574 = "P-457/4"
    P4578 = "P-457/8"
    P45736 = "P457/36"
    LEDIX_P260 = "ledix touch control P260"
    ROP21 = "ROP-21"
    ROP22 = "ROP-22"
    SRP22 = "SRP-22"
    RDP21 = "RDP-21"
    GKN01 = "GKN-01"
    ROP27 = "ROP-27"
    RGT01 = "RGT-01"
    RNM24 = "RNM-24"
    RNP21 = "RNP-21"
    RNP22 = "RNP-22"
    RCT21 = "RCT-21"
    RCT22 = "RCT-22"
    ROG21 = "ROG-21"
    ROM22 = "ROM-22"
    ROM24 = "ROM-24"
    SRM22 = "SRM-22"
    SLR21 = "SLR-21"
    SLR22 = "SLR-22"
    SLN21 = "SLN-21"
    SLN22 = "SLN-22"
    RCM21 = "RCM-21"
    MEM21 = "MEM-21"
    RCR21 = "RCR-21"
    RCZ21 = "RCZ-21"
    RCW21 = "RCW-21"
    SLM21 = "SLM-21"
    SLM22 = "SLM-22"
    RCK21 = "RCK-21"
    ROB21 = "ROB-21"
    REP21 = "REP-21"
    P501 = "P-501"
    P520 = "P-520"
    P521L = "P-521L"
    BULIK_DRS985 = "bulik DRS-985"

# Exta Free
    ROP01 = "ROP-01"
    ROP02 = "ROP-02"
    ROM01 = "ROM-01"
    ROM10 = "ROM-10"
    ROP05 = "ROP-05"
    ROP06 = "ROP-06"
    ROP07 = "ROP-07"
    RWG01 = "RWG-01"
    ROB01 = "ROB-01"
    SRP02 = "SRP-02"
    RDP01 = "RDP-01"
    RDP02 = "RDP-02"
    RDP11 = "RDP-11"
    SRP03 = "SRP-03"


class ExtaLifeDeviceModel(IntEnum):
    RNK22 = 1
    RNK22_TEMP_SENSOR = 2
    RNK24 = 3
    RNK24_TEMP_SENSOR = 4
    P4572 = 5
    P4574 = 6
    P4578 = 7
    P45736 = 8
    LEDIX_P260 = 9
    ROP21 = 10
    ROP22 = 11
    SRP22 = 12
    RDP21 = 13
    GKN01 = 14
    ROP27 = 15
    RGT01 = 16
    RNM24 = 17
    RNP21 = 18
    RNP22 = 19
    RCT21 = 20
    RCT22 = 21
    ROG21 = 22
    ROM22 = 23
    ROM24 = 24
    SRM22 = 25
    SLR21 = 26
    SLR22 = 27
    RCM21 = 28
    MEM21 = 35
    RCR21 = 41
    RCZ21 = 42
    SLN21 = 45
    SLN22 = 46
    RCK21 = 47
    ROB21 = 48
    P501 = 51
    P520 = 52
    P521L = 53
    RCW21 = 131
    REP21 = 237
    BULIK_DRS985 = 238

    ROP01 = 326
    ROP02 = 327
    ROM01 = 328
    ROM10 = 329
    ROP05 = 330
    ROP06 = 331
    ROP07 = 332
    RWG01 = 333
    ROB01 = 334
    SRP02 = 335
    RDP01 = 336
    RDP02 = 337
    RDP11 = 338
    SRP03 = 339


class ExtaLifeDeviceInfo:

    # device types string mapping
    __model_to_name_map: dict[ExtaLifeDeviceModel, ExtaLifeDeviceModelName] = {
        ExtaLifeDeviceModel.RNK22: ExtaLifeDeviceModelName.RNK22,
        ExtaLifeDeviceModel.RNK22_TEMP_SENSOR: ExtaLifeDeviceModelName.RNK22_TEMP_SENSOR,
        ExtaLifeDeviceModel.RNK24: ExtaLifeDeviceModelName.RNK24,
        ExtaLifeDeviceModel.RNK24_TEMP_SENSOR: ExtaLifeDeviceModelName.RNK24_TEMP_SENSOR,
        ExtaLifeDeviceModel.P4572: ExtaLifeDeviceModelName.P4572,
        ExtaLifeDeviceModel.P4574: ExtaLifeDeviceModelName.P4574,
        ExtaLifeDeviceModel.P4578: ExtaLifeDeviceModelName.P4578,
        ExtaLifeDeviceModel.P45736: ExtaLifeDeviceModelName.P45736,
        ExtaLifeDeviceModel.LEDIX_P260: ExtaLifeDeviceModelName.LEDIX_P260,
        ExtaLifeDeviceModel.ROP21: ExtaLifeDeviceModelName.ROP21,
        ExtaLifeDeviceModel.ROP22: ExtaLifeDeviceModelName.ROP22,
        ExtaLifeDeviceModel.SRP22: ExtaLifeDeviceModelName.SRP22,
        ExtaLifeDeviceModel.RDP21: ExtaLifeDeviceModelName.RDP21,
        ExtaLifeDeviceModel.GKN01: ExtaLifeDeviceModelName.GKN01,
        ExtaLifeDeviceModel.ROP27: ExtaLifeDeviceModelName.ROP27,
        ExtaLifeDeviceModel.RGT01: ExtaLifeDeviceModelName.RGT01,
        ExtaLifeDeviceModel.RNM24: ExtaLifeDeviceModelName.RNM24,
        ExtaLifeDeviceModel.RNP21: ExtaLifeDeviceModelName.RNP21,
        ExtaLifeDeviceModel.RNP22: ExtaLifeDeviceModelName.RNP22,
        ExtaLifeDeviceModel.RCT21: ExtaLifeDeviceModelName.RCT21,
        ExtaLifeDeviceModel.RCT22: ExtaLifeDeviceModelName.RCT22,
        ExtaLifeDeviceModel.ROG21: ExtaLifeDeviceModelName.ROG21,
        ExtaLifeDeviceModel.ROM22: ExtaLifeDeviceModelName.ROM22,
        ExtaLifeDeviceModel.ROM24: ExtaLifeDeviceModelName.ROM24,
        ExtaLifeDeviceModel.SRM22: ExtaLifeDeviceModelName.SRM22,
        ExtaLifeDeviceModel.SLR21: ExtaLifeDeviceModelName.SLR21,
        ExtaLifeDeviceModel.SLR22: ExtaLifeDeviceModelName.SLR22,
        ExtaLifeDeviceModel.RCM21: ExtaLifeDeviceModelName.RCM21,
        ExtaLifeDeviceModel.MEM21: ExtaLifeDeviceModelName.MEM21,
        ExtaLifeDeviceModel.RCR21: ExtaLifeDeviceModelName.RCR21,
        ExtaLifeDeviceModel.RCZ21: ExtaLifeDeviceModelName.RCZ21,
        ExtaLifeDeviceModel.SLN21: ExtaLifeDeviceModelName.SLN21,
        ExtaLifeDeviceModel.SLN22: ExtaLifeDeviceModelName.SLN22,
        ExtaLifeDeviceModel.RCK21: ExtaLifeDeviceModelName.RCK21,
        ExtaLifeDeviceModel.ROB21: ExtaLifeDeviceModelName.ROB21,
        ExtaLifeDeviceModel.P501: ExtaLifeDeviceModelName.P501,
        ExtaLifeDeviceModel.P520: ExtaLifeDeviceModelName.P520,
        ExtaLifeDeviceModel.P521L: ExtaLifeDeviceModelName.P521L,
        ExtaLifeDeviceModel.RCW21: ExtaLifeDeviceModelName.RCW21,
        ExtaLifeDeviceModel.REP21: ExtaLifeDeviceModelName.REP21,
        ExtaLifeDeviceModel.BULIK_DRS985: ExtaLifeDeviceModelName.BULIK_DRS985,

        # Exta Free
        ExtaLifeDeviceModel.ROP01: ExtaLifeDeviceModelName.ROP01,
        ExtaLifeDeviceModel.ROP02: ExtaLifeDeviceModelName.ROP02,
        ExtaLifeDeviceModel.ROM01: ExtaLifeDeviceModelName.ROM01,
        ExtaLifeDeviceModel.ROM10: ExtaLifeDeviceModelName.ROM10,
        ExtaLifeDeviceModel.ROP05: ExtaLifeDeviceModelName.ROP05,
        ExtaLifeDeviceModel.ROP06: ExtaLifeDeviceModelName.ROP06,
        ExtaLifeDeviceModel.ROP07: ExtaLifeDeviceModelName.ROP07,
        ExtaLifeDeviceModel.RWG01: ExtaLifeDeviceModelName.RWG01,
        ExtaLifeDeviceModel.ROB01: ExtaLifeDeviceModelName.ROB01,
        ExtaLifeDeviceModel.SRP02: ExtaLifeDeviceModelName.SRP02,
        ExtaLifeDeviceModel.RDP01: ExtaLifeDeviceModelName.RDP01,
        ExtaLifeDeviceModel.RDP02: ExtaLifeDeviceModelName.RDP02,
        ExtaLifeDeviceModel.RDP11: ExtaLifeDeviceModelName.RDP11,
        ExtaLifeDeviceModel.SRP03: ExtaLifeDeviceModelName.SRP03
    }

    __name_to_model_map: dict[ExtaLifeDeviceModelName, ExtaLifeDeviceModel] = {
        v: k for k, v in __model_to_name_map.items()
    }

    @classmethod
    def get_model_name(cls, device_type: ExtaLifeDeviceModel) -> ExtaLifeDeviceModelName:

        if device_type in cls.__model_to_name_map:
            return cls.__model_to_name_map.get(device_type)

        return ExtaLifeDeviceModelName(f"unknown device model ({device_type})")

    @classmethod
    def get_device_type(cls, model_name: ExtaLifeDeviceModelName) -> ExtaLifeDeviceModel:

        if model_name in cls.__name_to_model_map:
            return cls.__name_to_model_map.get(model_name)

        return ExtaLifeDeviceModel(0)


# Exta Life devices
DEVICE_ARR_SENS_TEMP = [
    ExtaLifeDeviceModel.RNK22_TEMP_SENSOR,
    ExtaLifeDeviceModel.RNK24_TEMP_SENSOR,
    ExtaLifeDeviceModel.RCT21,
    ExtaLifeDeviceModel.RCT22
]

DEVICE_ARR_SENS_LIGHT = []
DEVICE_ARR_SENS_HUMID = []
DEVICE_ARR_SENS_PRESSURE = []

DEVICE_ARR_SENS_MULTI = [
    ExtaLifeDeviceModel.RCM21
]

DEVICE_ARR_SENS_WATER = [
    ExtaLifeDeviceModel.RCZ21
]

DEVICE_ARR_SENS_MOTION = [
    ExtaLifeDeviceModel.RCR21
]

DEVICE_ARR_SENS_OPEN_CLOSE = [
    ExtaLifeDeviceModel.RCK21
]

DEVICE_ARR_SENS_ENERGY_METER = [
    ExtaLifeDeviceModel.MEM21
]

DEVICE_ARR_SENS_GATE_CONTROLLER = [
    ExtaLifeDeviceModel.ROB21
]

DEVICE_ARR_SWITCH = [
    ExtaLifeDeviceModel.ROP21,
    ExtaLifeDeviceModel.ROP22,
    ExtaLifeDeviceModel.ROG21,
    ExtaLifeDeviceModel.ROM22,
    ExtaLifeDeviceModel.ROM24
]
DEVICE_ARR_COVER = [
    ExtaLifeDeviceModel.SRP22,
    ExtaLifeDeviceModel.SRM22
]
DEVICE_ARR_LIGHT = [
    ExtaLifeDeviceModel.RDP21,
    ExtaLifeDeviceModel.SLR21,
    ExtaLifeDeviceModel.SLN21,
    ExtaLifeDeviceModel.SLR22,
    ExtaLifeDeviceModel.SLN22
]

DEVICE_ARR_LIGHT_RGB = []  # RGB only

DEVICE_ARR_LIGHT_RGBW = [
    ExtaLifeDeviceModel.SLR22,
    ExtaLifeDeviceModel.SLN22
]

DEVICE_ARR_LIGHT_EFFECT = [
    ExtaLifeDeviceModel.SLR22,
    ExtaLifeDeviceModel.SLN22
]

DEVICE_ARR_CLIMATE = [
    ExtaLifeDeviceModel.RGT01
]

DEVICE_ARR_REPEATER = [
    ExtaLifeDeviceModel.REP21
]

DEVICE_ARR_TRANS_REMOTE = [
    ExtaLifeDeviceModel.P4572,
    ExtaLifeDeviceModel.P4574,
    ExtaLifeDeviceModel.P4578,
    ExtaLifeDeviceModel.P45736,
    ExtaLifeDeviceModel.P501,
    ExtaLifeDeviceModel.P520,
    ExtaLifeDeviceModel.P521L
]

DEVICE_ARR_TRANS_NORMAL_BATTERY = [
    ExtaLifeDeviceModel.RNK22,
    ExtaLifeDeviceModel.RNK24,
    ExtaLifeDeviceModel.RNP22
]

DEVICE_ARR_TRANS_NORMAL_MAINS = [
    ExtaLifeDeviceModel.RNM24,
    ExtaLifeDeviceModel.RNP21
]

# Exta Free devices
DEVICE_ARR_EXTA_FREE_RECEIVER = [
    80
]

DEVICE_ARR_EXTA_FREE_SWITCH = [
    ExtaLifeDeviceModel.ROP01,
    ExtaLifeDeviceModel.ROP02,
    ExtaLifeDeviceModel.ROM01,
    ExtaLifeDeviceModel.ROM10,
    ExtaLifeDeviceModel.ROP05,
    ExtaLifeDeviceModel.ROP06,
    ExtaLifeDeviceModel.ROP07,
    ExtaLifeDeviceModel.RWG01,
    ExtaLifeDeviceModel.ROB01,
]

DEVICE_ARR_EXTA_FREE_COVER = [
    ExtaLifeDeviceModel.SRP02,
    ExtaLifeDeviceModel.SRP03
]

DEVICE_ARR_EXTA_FREE_LIGHT = [
    ExtaLifeDeviceModel.RDP01,
    ExtaLifeDeviceModel.RDP02
]

DEVICE_ARR_EXTA_FREE_RGB = [
    ExtaLifeDeviceModel.RDP11
]

DEVICE_ARR_ALL_EXTA_FREE_SWITCH = [*DEVICE_ARR_EXTA_FREE_SWITCH]
DEVICE_ARR_ALL_EXTA_FREE_LIGHT = [*DEVICE_ARR_EXTA_FREE_LIGHT, *DEVICE_ARR_EXTA_FREE_RGB]
DEVICE_ARR_ALL_EXTA_FREE_COVER = [*DEVICE_ARR_EXTA_FREE_COVER]

# union of all subtypes
DEVICE_ARR_ALL_SWITCH = [
    *DEVICE_ARR_SWITCH,
    *DEVICE_ARR_ALL_EXTA_FREE_SWITCH
]

DEVICE_ARR_ALL_LIGHT = [
    *DEVICE_ARR_LIGHT,
    *DEVICE_ARR_LIGHT_RGB,
    *DEVICE_ARR_LIGHT_RGBW,
    *DEVICE_ARR_ALL_EXTA_FREE_LIGHT,
]

DEVICE_ARR_ALL_COVER = [
    *DEVICE_ARR_COVER,
    *DEVICE_ARR_SENS_GATE_CONTROLLER,
    *DEVICE_ARR_ALL_EXTA_FREE_COVER
]

DEVICE_ARR_ALL_CLIMATE = [
    *DEVICE_ARR_CLIMATE
]

DEVICE_ARR_ALL_TRANSMITTER = [
    *DEVICE_ARR_TRANS_REMOTE,
    *DEVICE_ARR_TRANS_NORMAL_BATTERY,
    *DEVICE_ARR_TRANS_NORMAL_MAINS
]

DEVICE_ARR_ALL_IGNORE = [
    *DEVICE_ARR_REPEATER
]

# measurable magnitude/quantity:
DEVICE_ARR_ALL_SENSOR_MEAS = [
    *DEVICE_ARR_SENS_TEMP,
    *DEVICE_ARR_SENS_HUMID,
    *DEVICE_ARR_SENS_ENERGY_METER
]

# binary sensors:
DEVICE_ARR_ALL_SENSOR_BINARY = [
    *DEVICE_ARR_SENS_WATER,
    *DEVICE_ARR_SENS_MOTION,
    *DEVICE_ARR_SENS_OPEN_CLOSE,
]

DEVICE_ARR_ALL_SENSOR_MULTI = [
    *DEVICE_ARR_SENS_MULTI
]

DEVICE_ARR_ALL_SENSOR = [
    *DEVICE_ARR_ALL_SENSOR_MEAS,
    *DEVICE_ARR_ALL_SENSOR_BINARY,
    *DEVICE_ARR_ALL_SENSOR_MULTI,
]

# list of device types mapped into `light` platform in HA
# override device and type rules based on icon; force 'light' device for some icons,
# but only when device was detected preliminary as switch; 28 =LED
DEVICE_ICON_ARR_LIGHT = [
    8,
    9,
    13,
    14,
    15,
    16,
    17
]

try:
    from .fake_channels import FAKE_RECEIVERS, FAKE_SENSORS, FAKE_TRANSMITTERS      # pylint: disable=unused-import
except ImportError:
    FAKE_RECEIVERS = FAKE_SENSORS = FAKE_TRANSMITTERS = []


class ExtaLifeCmd(IntEnum):
    """ Supported Exta Life controller commands"""

    NOOP = 0
    LOGIN = 1
    CONTROL_DEVICE = 20
    FETCH_RECEIVERS = 37
    FETCH_SENSORS = 38
    FETCH_TRANSMITTERS = 39
    ACTIVATE_SCENE = 44
    FETCH_NETWORK_SETTINGS = 102
    FETCH_EXTA_FREE = 203
    RESTART = 150
    VERSION = 151


class ExtaLifeAPI:
    """ Main API class: wrapper for communication with controller """

    # Actions
    ACTION_TURN_ON = "TURN_ON"
    ACTION_TURN_OFF = "TURN_OFF"
    ACTION_SET_BRI = "SET_BRIGHTNESS"
    ACTION_SET_RGB = "SET_COLOR"
    ACTION_SET_POS = "SET_POSITION"
    ACTION_SET_GATE_POS = "SET_GATE_POSITION"
    ACTION_SET_TMP = "SET_TEMPERATURE"
    ACTION_STOP = "STOP"
    ACTION_OPEN = "UP"
    ACTION_CLOSE = "DOWN"
    ACTION_SET_SLR_MODE = "SET_MODE"
    ACTION_SET_RGT_MODE_MANUAL = "RGT_SET_MODE_MANUAL"
    ACTION_SET_RGT_MODE_AUTO = "RGT_SET_MODE_AUTO"

    # Exta Free Actions
    ACTION_EXTA_FREE_TURN_ON_PRESS = "TURN_ON_PRESS"
    ACTION_EXTA_FREE_TURN_ON_RELEASE = "TURN_ON_RELEASE"
    ACTION_EXTA_FREE_TURN_OFF_PRESS = "TURN_OFF_PRESS"
    ACTION_EXTA_FREE_TURN_OFF_RELEASE = "TURN_OFF_RELEASE"
    ACTION_EXTA_FREE_UP_PRESS = "UP_PRESS"
    ACTION_EXTA_FREE_UP_RELEASE = "UP_RELEASE"
    ACTION_EXTA_FREE_DOWN_PRESS = "DOWN_PRESS"
    ACTION_EXTA_FREE_DOWN_RELEASE = "DOWN_RELEASE"
    ACTION_EXTA_FREE_BRIGHT_UP_PRESS = "BRIGHT_UP_PRESS"
    ACTION_EXTA_FREE_BRIGHT_UP_RELEASE = "BRIGHT_UP_RELEASE"
    ACTION_EXTA_FREE_BRIGHT_DOWN_PRESS = "BRIGHT_DOWN_PRESS"
    ACTION_EXTA_FREE_BRIGHT_DOWN_RELEASE = "BRIGHT_DOWN_RELEASE"

    # Channel Types
    CHN_TYP_RECEIVERS = "receivers"
    CHN_TYP_SENSORS = "sensors"
    CHN_TYP_TRANSMITTERS = "transmitters"
    CHN_TYP_EXTA_FREE_RECEIVERS = "exta_free_receivers"

    _debugger: bool | None = None

    @classmethod
    def is_debugger_active(cls) -> bool:
        """Return if the debugger is currently active"""

        if cls._debugger is None:
            cls._debugger = hasattr(sys, "gettrace") and sys.gettrace() is not None
            if not cls._debugger:
                debugger_tool = sys.monitoring.get_tool(sys.monitoring.DEBUGGER_ID)
                cls._debugger = debugger_tool is not None and debugger_tool != ""

        return cls._debugger

    # TODO: APIResponse not dict[str, Any]
    def __init__(self, loop: AbstractEventLoop,
                 on_connect_callback: Callable[[], Awaitable] | None = None,
                 on_disconnect_callback: Callable[[], Awaitable] | None = None,
                 on_notification_callback: Callable[[dict[str, Any]], Awaitable] | None = None):
        """ API Object constructor
        on_connect - optional callback for notifications when API connects to the controller and performs
                    successful login

        on_disconnect - optional callback for notifications when API loses connection to the controller """

        self.tcp: TCPAdapter | None = None
        self._mac: str | None = None
        self._sw_version: str | None = None
        self._name: str | None = None

        # set on_connect callback to notify caller
        self._on_connect_callback: Callable[[], Awaitable] | None = on_connect_callback
        self._on_disconnect_callback: Callable[[], Awaitable] | None = on_disconnect_callback
        # TODO: APIResponse not dict[str, Any]
        self._on_notification_callback: Callable[[dict[str, Any]], Awaitable] | None = on_notification_callback

        self._is_connected = False

        self._loop: AbstractEventLoop = loop

        self._host: str | None = None
        self._user: str | None = None
        self._password: str | None = None
        self._connection: TCPAdapter | None = None

    async def async_connect(self, user: str, password: str, host: str | None = None, timeout: float = 30.0) -> bool:
        """Connect & authenticate to the controller using user and password parameters"""
        self._host = host
        self._user = user
        self._password = password

        # perform controller autodiscovery if no IP specified
        if self._host is None or self._host == "":
            future = await self._loop.run_in_executor(None, TCPAdapter.discover_controller)
            self._host = future.result()

        # check if still None after autodiscovery
        if not self._host:
            raise TCPConnError("Could not find controller IP via autodiscovery")

        conn_params = ConnectionParams(self._host, self._user, self._password, self._loop)
        conn_params.on_connected_callback = self._async_do_tcp_connected_callback
        conn_params.on_disconnected_callback = self._async_do_tcp_disconnected_callback
        conn_params.on_notification_callback = self._async_do_tcp_notification_callback

        # init TCP adapter and try to connect
        self._connection: TCPAdapter = TCPAdapter(conn_params)

        # connect and login - may raise TCPConnErr
        _LOGGER.debug("Connecting to controller using IP: %s", self._host)
        await self._connection.async_connect(timeout)

        resp = await self._connection.async_login()

        # check response if login succeeded
        if resp[0]["status"] != APIStatus.SUCCESS:
            raise TCPConnError(resp)

        # determine controller MAC as its unique identifier
        self._mac = await self.async_get_mac()

        return True

    async def async_reconnect(self):
        """ Reconnect with existing connection parameters """

        try:
            await self.async_connect(self._user, self._password, self._host, 10.0)
        except TCPConnError as err:
            _LOGGER.warning("Reconnect to EFC-01 at address %s failed. %s", self._host, err)

    @property
    def host(self):
        return self._host

    async def _async_do_tcp_connected_callback(self) -> None:
        """ Called when connectivity is (re)established and logged on successfully """
        self._is_connected = True
        # refresh software version info
        await self.async_get_version_info()
        await self.async_get_name()

        if self._on_connect_callback is not None:
            # await self._loop.run_in_executor(None, self._on_connect_callback)
            await self._on_connect_callback()

    async def _async_do_tcp_disconnected_callback(self) -> None:
        """ Called when connectivity is lost """
        self._is_connected = False

        if self._on_disconnect_callback is not None:
            # await self._loop.run_in_executor(None, self._on_disconnect_callback)
            await self._on_disconnect_callback()

    # TODO: APIResponse not dict[str, Any]
    async def _async_do_tcp_notification_callback(self, data: dict[str, Any]) -> None:
        """ Called when notification from the controller is received """

        if self._on_notification_callback is not None:
            # forward only device status changes to the listener
            await self._on_notification_callback(data)

    def set_notification_callback(self, notification_callback):
        """ update Notification callback assignment """
        self._on_notification_callback = notification_callback

    @property
    def is_connected(self) -> bool:
        """ Returns True or False depending of the connection is alive and user is logged on """
        return self._is_connected

    @classmethod
    def discover_controller(cls):
        """ Returns controller IP address if found, otherwise None"""
        return TCPAdapter.discover_controller()

    @property
    def sw_version(self) -> str:
        return self._sw_version

    async def async_get_version_info(self):
        """ Get controller software version """

        try:
            resp = await self._connection.async_execute_command(ExtaLifeCmd.VERSION, None)
            self._sw_version = resp[0]["data"]["new_version"]
            return self._sw_version

        except TCPCmdError:
            _LOGGER.error("Command %s could not be executed", ExtaLifeCmd.VERSION)
            return

    async def async_get_mac(self):
        from getmac import get_mac_address
        # get EFC-01 controller MAC address
        return await self._loop.run_in_executor(None, get_mac_address, None, self._host, None, self._host)

    @property
    def mac(self):
        return self._mac

    async def async_get_network_settings(self):
        """ Executes command 102 to get network settings and controller name """

        cmd: ExtaLifeCmd = ExtaLifeCmd.FETCH_NETWORK_SETTINGS
        try:
            resp = await self._connection.async_execute_command(cmd, None)
            return resp[0].get("data")

        except TCPCmdError:
            _LOGGER.error("Command %s could not be executed", cmd)
            return None

    async def async_get_name(self):
        """ Get controller name """
        data = await self.async_get_network_settings()
        self._name = data.get("name") if data else None
        return self._name

    @property
    def name(self) -> str:
        """ Get controller name from buffer """
        return self._name

    async def async_get_channels(self, include=(CHN_TYP_RECEIVERS, CHN_TYP_SENSORS, CHN_TYP_TRANSMITTERS,
                                                CHN_TYP_EXTA_FREE_RECEIVERS)) -> list | None:
        """
        Get list of dicts of Exta Life channels consisting of native Exta Life TCP JSON
        data, but with transformed data model. Each channel will have native channel info
        AND device info. 2 channels of the same device will have the same device attributes
        """
        cmd: ExtaLifeCmd = ExtaLifeCmd.NOOP
        try:
            channels = list()
            if self.CHN_TYP_RECEIVERS in include:
                cmd = ExtaLifeCmd.FETCH_RECEIVERS
                resp = await self._connection.async_execute_command(cmd, None)
                # here is where the magic happens - transform TCP JSON data into API channel representation
                resp.extend(FAKE_RECEIVERS)
                channels.extend(self._get_channels_int(resp))

            if self.CHN_TYP_SENSORS in include:
                cmd = ExtaLifeCmd.FETCH_SENSORS
                resp = await self._connection.async_execute_command(cmd, None)
                resp.extend(FAKE_SENSORS)
                channels.extend(self._get_channels_int(resp))

            if self.CHN_TYP_TRANSMITTERS in include:
                cmd = ExtaLifeCmd.FETCH_TRANSMITTERS
                resp = await self._connection.async_execute_command(cmd, None)
                channels.extend(self._get_channels_int(resp, dummy_ch=True))

            if self.CHN_TYP_EXTA_FREE_RECEIVERS in include:
                cmd = ExtaLifeCmd.FETCH_EXTA_FREE
                resp = await self._connection.async_execute_command(cmd, None)
                channels.extend(self._get_channels_int(resp))

            return channels

        except TCPConnError as err:
            _LOGGER.error("Command %s could not be executed, %s", cmd, err.data)
            return None

        except TCPCmdError as err:
            _LOGGER.error("Command %s could not be executed, %s", cmd, err.data)
            return None

    @classmethod
    def _get_channels_int(cls, data_js, dummy_ch=False):
        """
        data_js - list of TCP command data in JSON dict
        dummy_ch - dummy channel number? For Transmitters there is no channel info. Make it # per device

        The method will transform TCP JSON into list of channels.
        Each channel will look like rephrased TCP JSON and will consist of attributes
        of the "state" section (channel) + attributes of the "device" section
        e.g.:

        "devices": [{
           "id": 11,
           "is_powered": false,
           "is_paired": false,
           "set_remove_sensor": false,
           "device": 1,
           "type": 11,
           "serial": 725149,
           "state": [{
              "alias": "Room 1-1",
              "channel": 1,
              "icon": 13,
              "is_timeout": false,
              "fav": null,
              "power": 0,
              "last_dir": null,
              "value": null
           }
        }

        will become:
        [{
           "id": "11-1",
           "data": {
              "alias": "Room 1-1",
              "channel": 1,
              "icon": 13,
              "is_timeout": false,
              "fav": null,
              "power": 0,
              "last_dir": null,
              "value": null,
              "id": 11,
              "is_powered": false,
              "is_paired": false,
              "set_remove_sensor": false,
              "device": 1,
              "type": 11,
              "serial": 725149
           }
        }]
        """

        def_channel = None
        if dummy_ch:
            def_channel = '#'
        channels = []  # list of JSON dicts
        for cmd in data_js:
            for device in cmd["data"]["devices"]:
                dev = device.copy()

                if dev.get("exta_free_device") is True:
                    # do the same as the Exta Life app does - add 300 to move identifiers to Exta Life "namespace"
                    dev["type"] = int(dev["state"][0]["exta_free_type"]) + 300

                dev.pop("state")
                for state in device["state"]:
                    # ch_no = state.get("channel", def_channel) if def_channel else state["channel"]
                    channel = {
                        # API channel, not TCP channel
                        "id": str(device["id"]) + "-" + str(state.get("channel", def_channel)),
                        "data": {**state, **dev}
                    }
                    channels.append(channel)
        return channels

    async def async_execute_action(self, action, channel_id, **fields):
        """Execute action/command in controller
        action - action to be performed. See ACTION_* constants
        channel_id - concatenation of device id and channel number e.g. '1-1'
        **fields - fields of the native JSON command e.g. value, mode, mode_val etc

        Returns array of dicts converted from JSON or None if error occurred
        """
        map_action_state = {
            # Exta Life:
            ExtaLifeAPI.ACTION_TURN_ON: 1,
            ExtaLifeAPI.ACTION_TURN_OFF: 0,
            ExtaLifeAPI.ACTION_OPEN: 1,
            ExtaLifeAPI.ACTION_CLOSE: 0,
            ExtaLifeAPI.ACTION_STOP: 2,
            ExtaLifeAPI.ACTION_SET_POS: None,
            ExtaLifeAPI.ACTION_SET_GATE_POS: 1,
            ExtaLifeAPI.ACTION_SET_RGT_MODE_AUTO: 0,
            ExtaLifeAPI.ACTION_SET_RGT_MODE_MANUAL: 1,
            ExtaLifeAPI.ACTION_SET_TMP: 1,
            # Exta Free:
            ExtaLifeAPI.ACTION_EXTA_FREE_TURN_ON_PRESS: 1,
            ExtaLifeAPI.ACTION_EXTA_FREE_TURN_ON_RELEASE: 2,
            ExtaLifeAPI.ACTION_EXTA_FREE_TURN_OFF_PRESS: 3,
            ExtaLifeAPI.ACTION_EXTA_FREE_TURN_OFF_RELEASE: 4,
            ExtaLifeAPI.ACTION_EXTA_FREE_UP_PRESS: 1,
            ExtaLifeAPI.ACTION_EXTA_FREE_UP_RELEASE: 2,
            ExtaLifeAPI.ACTION_EXTA_FREE_DOWN_PRESS: 3,
            ExtaLifeAPI.ACTION_EXTA_FREE_DOWN_RELEASE: 4,
            ExtaLifeAPI.ACTION_EXTA_FREE_BRIGHT_UP_PRESS: 1,
            ExtaLifeAPI.ACTION_EXTA_FREE_BRIGHT_UP_RELEASE: 2,
            ExtaLifeAPI.ACTION_EXTA_FREE_BRIGHT_DOWN_PRESS: 3,
            ExtaLifeAPI.ACTION_EXTA_FREE_BRIGHT_DOWN_RELEASE: 4,
        }
        ch_id, channel = channel_id.split("-")
        ch_id = int(ch_id)
        channel = int(channel)

        cmd_data = {
            "id": ch_id,
            "channel": channel,
            "state": map_action_state.get(action),
        }
        # this assumes the right fields are passed to the API
        cmd_data.update(**fields)

        cmd: ExtaLifeCmd = ExtaLifeCmd.CONTROL_DEVICE
        try:
            resp = await self._connection.async_execute_command(cmd, cmd_data)
            _LOGGER.debug("JSON response for command %s: %s", cmd, resp)
            return resp

        except TCPCmdError as err:
            # _LOGGER.error("Command %s could not be executed", cmd)
            _LOGGER.exception(err)
            return None

    async def async_restart(self):
        """ Restart EFC-01 """

        cmd: ExtaLifeCmd = ExtaLifeCmd.RESTART
        try:
            cmd_data = dict()

            resp = await self._connection.async_execute_command(cmd, cmd_data)

            _LOGGER.debug("JSON response for command %s: %s", cmd, resp)

            return resp
        except TCPCmdError:
            _LOGGER.error("Command %s could not be executed", cmd)
            return None

    async def disconnect(self):
        """ Disconnect from the controller and stop message tasks """
        await self._connection.async_stop(True)

    def get_tcp_adapter(self):
        return self._connection


class TCPConnError(Exception):
    def __init__(self, data=None, previous=None):
        super().__init__()
        self.data = data
        self.error_code = None
        self.previous = previous
        if data:
            data = data[-1].get("data") if isinstance(data[-1], dict) else None
            self.error_code = None if not data else data.get("code")


class TCPCmdError(Exception):
    def __init__(self, data=None):
        super().__init__()
        self.data = data
        self.error_code = None
        if data:
            data = data[-1].get("data") if isinstance(data[-1], dict) else None
            self.error_code = None if not data else data.get("code")


class ConnectionParams:

    def __init__(self, host: str, user: str, password: str, eventloop: AbstractEventLoop, keepalive: float = 8):
        self._eventloop: AbstractEventLoop = eventloop
        self._host: str = host
        self._user: str = user
        self._password: str = password
        self._keepalive: float = keepalive
        self.on_connected_callback: Callable[[], Awaitable] | None = None
        self.on_disconnected_callback: Callable[[], Awaitable] | None = None
        # TODO: APIResponse not dict[str, Any]
        self.on_notification_callback: Callable[[dict[str, Any]], Awaitable] | None = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def user(self) -> str:
        return self._user

    @property
    def password(self) -> str:
        return self._password

    @property
    def keepalive(self) -> float:
        return self._keepalive

    @property
    def eventloop(self) -> AbstractEventLoop:
        return self._eventloop


class APIMessage:
    def __init__(self, command: ExtaLifeCmd = ExtaLifeCmd.NOOP):
        self.command: ExtaLifeCmd = command
        self.data: dict[str, Any] = {"data": None}


class APIRequest(APIMessage):

    def __init__(self, command: ExtaLifeCmd, data: dict[str, Any] | None = None) -> None:
        super().__init__(command)
        self.command = command
        if data:
            self.data = data

    def as_dict(self):
        return {"command": self.command, "data": self.data}

    def as_json(self):
        return json.dumps(self.as_dict())

    def as_string(self) -> str:
        return str(self.as_json()) if self.command != ExtaLifeCmd.NOOP else " "

    def as_bytes(self) -> bytes:
        return (self.as_string() + chr(3)).encode()


class APIStatus(StrEnum):
    SUCCESS = "success"
    SEARCHING = "searching"
    FAILURE = "failure"
    PARTIAL = "partial"
    NOTIFICATION = "notification"


class APIResponse(APIMessage):

    def __init__(self, json_obj: dict[str, Any]) -> None:
        super().__init__(ExtaLifeCmd(json_obj.get("command")))
        self._as_dict: dict[str, Any] = json_obj
        self.data = json_obj.get("data")
        self.status: APIStatus = APIStatus(json_obj.get("status"))

    @classmethod
    def from_json(cls, json_str: str) -> "APIResponse":
        return APIResponse(json.loads(json_str[:-1]))

    def as_dict(self) -> dict[str, Any]:
        return self._as_dict


class TCPAdapter:

    TCP_BUFF_SIZE = 8192
    EFC01_PORT = 20400

    _cmd_in_execution = False

    def __init__(self, params: ConnectionParams) -> None:

        self._params: ConnectionParams = params
        self._connected: bool = False
        self._stopped: bool = False
        self._authenticated: bool = False
        self._tcp_reader: asyncio.StreamReader | None = None     # type asyncio.StreamReader
        self._tcp_writer: asyncio.StreamWriter | None = None     # type asyncio.StreamWriter
        self._write_lock: asyncio.Lock = asyncio.Lock()
        self._cmd_exec_lock: asyncio.Lock = asyncio.Lock()
        self._running_task = None
        self._socket = None
        self._socket_connected = False
        self._ping_task = None
        self._reader_task = None

        self._tcp_last_write = datetime.now()

        self._response_handlers: list[Callable[[APIResponse], None]] = []

    def _start_ping(self) -> None:
        """ Perform "smart" ping task. Send ping if nothing was sent to socket in the last keepalive-time period """

        self._ping_task = self._params.eventloop.create_task(self._ping_())

    async def _ping_(self) -> None:
        from datetime import datetime       # pylint disable=import-outside-toplevel
        while self._connected:
            last_write = (datetime.now() - self._tcp_last_write).seconds

            if last_write < self._params.keepalive:
                period = self._params.keepalive - last_write
                await asyncio.sleep(period)
                continue

            if not self._connected:
                break

            try:
                await self.async_ping()
            except TCPConnError:
                _LOGGER.error("%s: Ping Failed!", self._params.host)
                await self._async_on_error()
                break

        _LOGGER.debug("_ping_() - task ends")

    async def _async_post_data(self, data: bytes) -> None:
        from datetime import datetime
        if not self._socket_connected:
            raise TCPConnError("Socket is not connected")
        try:
            async with self._write_lock:
                self._tcp_writer.write(data)
                self._tcp_last_write = datetime.now()
                await self._tcp_writer.drain()
        except OSError as err:
            await self._async_on_error()
            raise TCPConnError("Error while writing data: {}".format(err)) from None

    async def async_post_request(self, request: APIRequest) -> None:    # pylint disable=raise-missing-from

        request_data = request.as_bytes()
        request_str = str(request_data)
        if request.command == ExtaLifeCmd.LOGIN and not ExtaLifeAPI.is_debugger_active():
            request_str = re.sub(r'"password":\s*"[^"]*"', '"password": "********"', request_str)
        _LOGGER.debug(">>> [Cmd=%s] %s", request.command.name, request_str)

        await self._async_post_data(request_data)

    # TODO: APIResponse not dict[str, Any]
    async def async_send_request(self, request: APIRequest,
                                 timeout: float = 30.0) -> list[dict[str, Any]]:
        """ Send message to controller and await response """
        # prevent controller overloading and command loss - wait until finished (lock released)
        async with self._cmd_exec_lock:
            fut = self._params.eventloop.create_future()
            responses = []

            def on_message(response: APIResponse) -> None:

                if fut.done() or response.command != request.command:
                    return

                _LOGGER.debug("on_message(), response for %s, status %s", response.command.name, response.status.name)

                if response.status == APIStatus.SEARCHING:
                    responses.append(response.as_dict())
                elif response.status in (APIStatus.SUCCESS, APIStatus.FAILURE, APIStatus.PARTIAL):
                    responses.append(response.as_dict())
                    fut.set_result(responses)

            self._response_handlers.append(on_message)
            await self.async_post_request(request)

            try:
                await asyncio.wait_for(fut, timeout)

            except asyncio.TimeoutError:
                if self._stopped:
                    raise TCPConnError("Disconnected while waiting for API response!") from None
                await self._async_on_error()
                raise TCPConnError("Timeout while waiting for API response!") from None

            try:
                self._response_handlers.remove(on_message)                          # pylint: disable=raise-missing-from
            except ValueError:
                pass

            return responses

    async def async_post_command(self, command: ExtaLifeCmd, data: dict[str, any] | None = None) -> None:
        await self.async_post_request(APIRequest(command, data))

    async def async_execute_command(self, command: ExtaLifeCmd, data: dict[str, any] | None = None) -> list:

        response = await self.async_send_request(APIRequest(command, data))

        if len(response) == 0:
            raise TCPConnError("No response received from Controller!")

        return response

    async def _async_recv(self) -> bytes:

        try:
            result = await self._tcp_reader.readuntil(chr(3).encode())
        except (asyncio.IncompleteReadError, OSError, TimeoutError) as err:
            raise TCPConnError("Error while receiving data: {}".format(err)) from err

        return result

    def _check_connected(self) -> None:
        if not self._connected:
            raise TCPConnError("Not connected!")

    async def _close_socket(self) -> None:
        _LOGGER.debug("entering _close_socket()")

        if not self._socket_connected:
            return
        async with self._write_lock:
            self._tcp_writer.close()
            self._tcp_writer = None
            self._tcp_reader = None
        if self._socket is not None:
            self._socket.close()

        self._socket_connected = False
        self._connected = False
        self._authenticated = False
        _LOGGER.debug("%s: Closed socket", self._params.host)

    async def async_connect(self, timeout: float = 30.0):
        """
        Connect to EFC-01 via TCP socket
        """
        if self._stopped:
            raise TCPConnError("Connection is closed!")
        if self._connected:
            raise TCPConnError("Already connected!")

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setblocking(False)
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        _LOGGER.debug("Connecting to %s:%s", self._params.host,
                      self.EFC01_PORT, )
        try:
            coro = self._params.eventloop.sock_connect(self._socket, (self._params.host, self.EFC01_PORT))
            await asyncio.wait_for(coro, timeout)
        except OSError as err:
            await self._async_on_error()
            raise TCPConnError(
                "Error connecting to {}: {}".format(self._params.host, err), previous=err) from err
        except asyncio.TimeoutError as err:
            await self._async_on_error()
            raise TCPConnError(
                "Timeout while connecting to {}".format(self._params.host)) from err

        _LOGGER.debug("%s: Opened socket for", self._params.host)
        self._tcp_reader, self._tcp_writer = await asyncio.open_connection(sock=self._socket)
        self._socket_connected = True

        # should await but this never return
        self._reader_task = self._params.eventloop.create_task(self.async_run_forever())

        _LOGGER.debug("Successfully connected ")

        self._connected = True

        self._start_ping()

    async def async_ping(self) -> None:
        """Perform dummy data posting to connected controller"""
        self._check_connected()
        await self.async_post_command(ExtaLifeCmd.NOOP)

    # TODO: APIResponse not list
    async def async_login(self) -> list:
        """
        Try to log on via command: 1
        return json dictionary with result or exception in case of connection or logon
        problem
        """

        self._check_connected()
        if self._authenticated:
            raise TCPConnError("Already logged in!")

        _LOGGER.debug("Logging in... [user: %s, password: %s]",
                      self._params.user, "*" * len(self._params.password))
        cmd_data = {
            "password": self._params.password,
            "login": self._params.user
        }
        resp_js = await self.async_execute_command(ExtaLifeCmd.LOGIN, cmd_data)

        if resp_js[0].get("status") == "failure" and resp_js[0].get("data").get("code") == -2:
            # pass
            raise TCPConnError("Invalid password!")

        self._authenticated = True

        _LOGGER.debug("Authenticated")

        await self._async_do_connected()

        return resp_js

    async def async_run_forever(self) -> None:
        _LOGGER.debug("Starting TCPAdapter reader")
        while True:
            try:
                await self._async_run_once()
            except TCPConnError as err:
                _LOGGER.info("Error while reading incoming messages: %s", err.data)
                await self._async_on_error()
                break
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.info("Unexpected error while reading incoming messages: %s", err)
                await self._async_on_error()
                break

        _LOGGER.debug("async_run_forever() - task ends")

    async def _async_run_once(self) -> None:

        message_raw = await self._async_recv()

        message_str = message_raw.decode()

        response: APIResponse = APIResponse.from_json(message_str)
        _LOGGER.debug("<<< [Cmd=%s] %s", response.command.name, message_str)

        for response_handler in self._response_handlers[:]:
            response_handler(response)

        # pass only status change notifications to registered listeners
        if response.status == APIStatus.NOTIFICATION and self._params.on_notification_callback is not None:
            await self._params.on_notification_callback(response.as_dict())

    async def _async_on_error(self) -> None:
        await self.async_stop(force=True)

    async def async_stop(self, force: bool = False) -> None:
        _LOGGER.debug("async_stop() self._stopped: %s", self._stopped)
        if self._stopped and not force:
            return

        self._stopped = True
        if self._running_task is not None:
            self._running_task.cancel()
            self._running_task = None

        if self._ping_task is not None:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError as err:
                _LOGGER.debug( "ping_task has been canceled, %s", err)
                pass
            self._ping_task = None

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError as err:
                _LOGGER.debug("reader_task has been canceled, %s", err)
                pass
            self._reader_task = None

        await self._close_socket()

        await self._async_do_disconnected()

    async def _async_do_connected(self):
        """ Notify of (re)connection by calling provided callback """
        if self._params.on_connected_callback is not None:
            await self._params.on_connected_callback()

    async def _async_do_disconnected(self):
        """ Notify of lost connection by calling provided callback """
        if self._params.on_disconnected_callback is not None:
            await self._params.on_disconnected_callback()

    @staticmethod
    def discover_controller():
        """
        Perform controller autodiscovery using UDP query
        return IP as string or false if not found
        """
        multicast_group: str = "225.0.0.1"
        multicast_port: int = 20401
        import struct

        # sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = ("", multicast_port)

        # Create the socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Bind to the server address
        try:
            sock.bind(server_address)
        except socket.error:
            sock.close()
            _LOGGER.error("Could not connect to receive UDP multicast from EFC-01 on port %s", multicast_port)
            return False

        # Tell the operating system to add the socket to the multicast group
        # on all interfaces (join multicast group)
        group = socket.inet_aton(multicast_group)
        multicast_req = struct.pack("4sL", group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, multicast_req)

        sock.settimeout(3)
        try:
            (data, address) = sock.recvfrom(1024)
        except socket.error:
            sock.close()
            return
        sock.close()

        _LOGGER.debug("Got multicast response from EFC-01: %s", str(data.decode()))

        if data == b'{"status":"broadcast","command":0,"data":null}\x03':
            return address[0]  # return IP - array[0]; array[1] is sender's port
        return
