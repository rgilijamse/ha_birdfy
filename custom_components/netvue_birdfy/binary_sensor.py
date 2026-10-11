"""Binary sensors for Netvue Birdfy feeders on the Addx platform."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BirdfyConfigEntry
from .entity import BirdfyEntity

# Addx isCharging: 0 = no power in, 1 = charging, 2 = full. chargingMode: 0 = no power in,
# 3 = solar panel (USB not seen yet). Matched against sunrise/sunset on a WS2900.
IS_CHARGING = 1


def _flag(key: str, on: Callable[[Any], bool]) -> Callable[[dict[str, Any]], bool | None]:
    def value(attributes: dict[str, Any]) -> bool | None:
        raw = attributes.get(key)
        return None if raw is None else on(raw)

    return value


@dataclass(frozen=True, kw_only=True)
class BirdfyBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[BirdfyBinarySensorDescription, ...] = (
    BirdfyBinarySensorDescription(
        key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_flag("online", lambda v: v == 1),
    ),
    BirdfyBinarySensorDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_flag("isCharging", lambda v: v == IS_CHARGING),
    ),
    BirdfyBinarySensorDescription(
        key="solar_power",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=_flag("chargingMode", lambda v: v != 0),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BirdfyBinarySensor(coordinator, serial, description)
        for serial in coordinator.data
        for description in BINARY_SENSORS
    )


class BirdfyBinarySensor(BirdfyEntity, BinarySensorEntity):
    """A flag from the feeder's Addx real-time attributes."""

    entity_description: BirdfyBinarySensorDescription

    def __init__(self, coordinator, serial: str, description: BirdfyBinarySensorDescription) -> None:
        super().__init__(coordinator, serial, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return super().available and self.state_data.attributes is not None

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.state_data.attributes)
