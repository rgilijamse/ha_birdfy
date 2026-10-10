"""Latest-snapshot image for Netvue Birdfy, served from the local archive."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import BirdfyConfigEntry
from .entity import BirdfyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LastSnapshotImage(coordinator, serial) for serial in coordinator.data)


class LastSnapshotImage(BirdfyEntity, ImageEntity):
    """Snapshot of the newest event."""

    _attr_content_type = "image/jpeg"

    def __init__(self, coordinator, serial: str) -> None:
        BirdfyEntity.__init__(self, coordinator, serial, "last_snapshot")
        ImageEntity.__init__(self, coordinator.hass)
        self._update_from_visit()

    def _update_from_visit(self) -> None:
        visit = self.state_data and self.state_data.last_visit
        self._attr_image_last_updated = visit.time if visit else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_visit()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        visit = self.state_data and self.state_data.last_visit
        if not visit:
            return None

        def read() -> bytes | None:
            return visit.snapshot.read_bytes() if visit.snapshot.exists() else None

        return await self.hass.async_add_executor_job(read)
