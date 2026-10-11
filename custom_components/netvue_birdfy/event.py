"""Visit event entity for Netvue Birdfy; fires once per newly archived event."""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BirdfyConfigEntry
from .const import EVENT_VISIT
from .entity import BirdfyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(VisitEvent(coordinator, serial) for serial in coordinator.data)


class VisitEvent(BirdfyEntity, EventEntity):
    """Fires for each new clip; the backfill after startup does not fire."""

    _attr_event_types = [EVENT_VISIT]

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "visit")

    @callback
    def _handle_coordinator_update(self) -> None:
        state = self.state_data
        for visit in state.new_visits if state else []:
            self._trigger_event(
                EVENT_VISIT,
                {
                    "alarm_id": visit.alarm_id,
                    "time": visit.time.isoformat(),
                    "species": visit.species,
                    "detected": visit.detected,
                    "video": self.coordinator.media_source_uri(visit.video),
                    "snapshot": self.coordinator.media_source_uri(visit.snapshot),
                },
            )
            self.async_write_ha_state()
        super()._handle_coordinator_update()
