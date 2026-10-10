"""Sensors for Netvue Birdfy."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import BirdfyConfigEntry
from .coordinator import BirdfyCoordinator, DeviceState
from .entity import BirdfyEntity

# eventCount tags that are totals or unidentified, not species.
NON_SPECIES_TAGS = {"AllBird", "Bird", "AllAnimal", "Animal"}
GROUP_BIRDS = 1


def _attr(key: str) -> Callable[[DeviceState], Any]:
    return lambda s: (s.attributes or {}).get(key)


def _sd(key: str) -> Callable[[DeviceState], Any]:
    return lambda s: ((s.attributes or {}).get("sdCard") or {}).get(key)


def _recent_species(state: DeviceState) -> dict[str, int]:
    return {
        c["tag"]: c["count"]
        for c in state.bird_counts or []
        if c.get("group") == GROUP_BIRDS and c.get("tag") not in NON_SPECIES_TAGS
    }


def _species_list(state: DeviceState) -> list[dict[str, Any]]:
    return [
        {
            "name": b.get("birdName"),
            "first_seen": dt_util.utc_from_timestamp(b["createTime"] / 1000).isoformat()
            if b.get("createTime")
            else None,
        }
        for b in (state.species or {}).get("birds", [])
    ]


@dataclass(frozen=True, kw_only=True)
class BirdfySensorDescription(SensorEntityDescription):
    value_fn: Callable[[DeviceState], Any]
    available_fn: Callable[[DeviceState], bool] = lambda s: True
    attrs_fn: Callable[[BirdfyCoordinator, DeviceState], dict[str, Any] | None] | None = None


def _last_visit_attrs(coordinator: BirdfyCoordinator, state: DeviceState) -> dict[str, Any] | None:
    visit = state.last_visit
    if not visit:
        return None
    return {
        "alarm_id": visit.alarm_id,
        "video": coordinator.media_source_uri(visit.video),
        "snapshot": coordinator.media_source_uri(visit.snapshot),
    }


SENSORS: tuple[BirdfySensorDescription, ...] = (
    BirdfySensorDescription(
        key="last_visit",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s: s.last_visit.time if s.last_visit else None,
        attrs_fn=_last_visit_attrs,
    ),
    BirdfySensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_attr("batteryLevel"),
        available_fn=lambda s: s.attributes is not None,
        # Raw codes until their meaning is known (seen: isCharging 2, chargingMode 3 at 100%).
        attrs_fn=lambda c, s: {
            "is_charging": _attr("isCharging")(s),
            "charging_mode": _attr("chargingMode")(s),
        },
    ),
    BirdfySensorDescription(
        key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_attr("signalStrength"),
        available_fn=lambda s: s.attributes is not None,
    ),
    BirdfySensorDescription(
        key="sd_card_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_sd("free"),
        available_fn=lambda s: bool((s.attributes or {}).get("sdCard")),
        attrs_fn=lambda c, s: {"total_mb": _sd("total")(s), "used_mb": _sd("used")(s)},
    ),
    BirdfySensorDescription(
        key="recent_species",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: len(_recent_species(s)),
        available_fn=lambda s: s.bird_counts is not None,
        attrs_fn=lambda c, s: {"counts": _recent_species(s)},
    ),
    BirdfySensorDescription(
        key="species_seen",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: (s.species or {}).get("total"),
        available_fn=lambda s: s.species is not None,
        attrs_fn=lambda c, s: {"species": _species_list(s)},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BirdfySensor(coordinator, serial, description)
        for serial in coordinator.data
        for description in SENSORS
    )


class BirdfySensor(BirdfyEntity, SensorEntity):
    """A sensor computed from the feeder's poll result."""

    entity_description: BirdfySensorDescription

    def __init__(
        self, coordinator: BirdfyCoordinator, serial: str, description: BirdfySensorDescription
    ) -> None:
        super().__init__(coordinator, serial, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.available_fn(self.state_data)

    @property
    def native_value(self) -> datetime | int | float | None:
        return self.entity_description.value_fn(self.state_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.entity_description.attrs_fn:
            return None
        return self.entity_description.attrs_fn(self.coordinator, self.state_data)
