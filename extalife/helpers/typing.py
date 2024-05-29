from typing import TYPE_CHECKING

DeviceType = "Device"
DeviceManagerType = "DeviceManager"
TransmitterManagerType = "TransmitterManager"
ChannelDataManagerType = "ChannelDataManager"
CoreType = "Core"
ExtaLifeTransmitterEventProcessorType = "ExtaLifeTransmitterEventProcessor"


if TYPE_CHECKING:
    from .device import Device, DeviceManager
    from ..transmitter import TransmitterManager
    from .. import ChannelDataManager
    from .core import Core
    DeviceType = Device
    DeviceManagerType = DeviceManager
    TransmitterManagerType = TransmitterManager
    ChannelDataManagerType = ChannelDataManager
    CoreType = Core
