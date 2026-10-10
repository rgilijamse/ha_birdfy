"""Online status for Netvue Birdfy feeders on the Addx platform."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BirdfyConfigEntry
from .entity import BirdfyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(OnlineSensor(coordinator, serial) for serial in coordinator.data)


class OnlineSensor(BirdfyEntity, BinarySensorEntity):
    """Whether the cloud sees the feeder as connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "online")

    @property
    def available(self) -> bool:
        return super().available and self.state_data.attributes is not None

    @property
    def is_on(self) -> bool | None:
        online = self.state_data.attributes.get("online")
        return None if online is None else online == 1
