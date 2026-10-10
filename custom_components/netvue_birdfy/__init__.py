"""Netvue Birdfy: archive feeder clips and snapshots into Home Assistant media."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NetvueClient
from .const import CONF_PASSWORD_MD5, CONF_UDID, CONF_USERID
from .coordinator import BirdfyCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.EVENT, Platform.IMAGE, Platform.SENSOR]

type BirdfyConfigEntry = ConfigEntry[BirdfyCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: BirdfyConfigEntry) -> bool:
    """Set up Birdfy from a config entry."""

    def save_token(token: str, userid: str) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_TOKEN: token, CONF_USERID: userid}
        )

    client = NetvueClient(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD_MD5],
        entry.data[CONF_UDID],
        token=entry.data.get(CONF_TOKEN),
        userid=entry.data.get(CONF_USERID),
        on_token=save_token,
    )
    coordinator = BirdfyCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BirdfyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
