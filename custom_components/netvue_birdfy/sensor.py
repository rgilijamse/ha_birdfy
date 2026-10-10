"""Last-visit sensor for Netvue Birdfy."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
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
    async_add_entities(LastVisitSensor(coordinator, serial) for serial in coordinator.data)


class LastVisitSensor(BirdfyEntity, SensorEntity):
    """Time of the newest event, with media-source links to its files."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "last_visit")

    @property
    def native_value(self) -> datetime | None:
        visit = self.state_data and self.state_data.last_visit
        return visit.time if visit else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        visit = self.state_data and self.state_data.last_visit
        if not visit:
            return None
        return {
            "alarm_id": visit.alarm_id,
            "video": self.coordinator.media_source_uri(visit.video),
            "snapshot": self.coordinator.media_source_uri(visit.snapshot),
        }
