"""Base entity for Netvue Birdfy."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import BirdfyCoordinator, DeviceState


class BirdfyEntity(CoordinatorEntity[BirdfyCoordinator]):
    """An entity tied to one feeder."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BirdfyCoordinator, serial: str, key: str) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = coordinator.data[serial].device_info

    @property
    def state_data(self) -> DeviceState | None:
        return self.coordinator.data.get(self._serial)

    @property
    def available(self) -> bool:
        return super().available and self.state_data is not None
