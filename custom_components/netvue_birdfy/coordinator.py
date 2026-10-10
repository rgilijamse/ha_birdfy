"""Polls the Netvue cloud and archives new clips and snapshots to disk."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util, slugify

from .api import NetvueAuthError, NetvueClient, NetvueError
from .const import CONF_FOLDER, DEFAULT_FOLDER, DOMAIN, LINK_BATCH, LOOKBACK, SCAN_INTERVAL

if TYPE_CHECKING:
    from . import BirdfyConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class Visit:
    """One motion event and where its files live on disk."""

    alarm_id: str
    time: datetime
    video: Path
    snapshot: Path

    @property
    def has_video(self) -> bool:
        return self.video.exists()

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot.exists()


@dataclass
class DeviceState:
    """Per-feeder result of one poll."""

    device: dict[str, Any]
    folder: Path
    last_visit: Visit | None = None
    new_visits: list[Visit] = field(default_factory=list)

    @property
    def serial(self) -> str:
        return self.device["serialNumber"]

    @property
    def device_info(self) -> DeviceInfo:
        info = DeviceInfo(
            identifiers={(DOMAIN, self.serial)},
            name=self.device.get("deviceName") or self.serial,
            manufacturer="Netvue",
            model=self.device.get("productCode"),
            serial_number=self.serial,
        )
        if mac := self.device.get("ethMacAddress"):
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
        return info


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class BirdfyCoordinator(DataUpdateCoordinator[dict[str, DeviceState]]):
    """Fetches recent events per feeder and downloads anything not yet on disk."""

    config_entry: BirdfyConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: BirdfyConfigEntry, client: NetvueClient
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.client = client
        media_dirs = hass.config.media_dirs
        media = media_dirs.get("local") or next(iter(media_dirs.values()), None)
        self.media_dir = Path(media or hass.config.path("media"))
        self.archive_dir = self.media_dir / entry.options.get(CONF_FOLDER, DEFAULT_FOLDER)
        self._backfilled = False

    def media_source_uri(self, path: Path) -> str:
        """Return the media-source URI for an archived file."""
        return f"media-source://media_source/local/{path.relative_to(self.media_dir).as_posix()}"

    async def _async_update_data(self) -> dict[str, DeviceState]:
        try:
            devices = await self.client.get_devices()
            states = {}
            for device in devices:
                state = await self._sync_device(device)
                states[state.serial] = state
        except NetvueAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NetvueError as err:
            raise UpdateFailed(str(err)) from err
        self._backfilled = True
        return states

    def _visit(self, folder: Path, event: dict[str, Any]) -> Visit:
        when = dt_util.as_local(dt_util.utc_from_timestamp(event["alertTime"] / 1000))
        base = folder / when.strftime("%Y-%m-%d") / f"{when:%H%M%S}_{event['alarmId']}"
        return Visit(
            alarm_id=event["alarmId"],
            time=when,
            video=base.with_suffix(".mp4"),
            snapshot=base.with_suffix(".jpg"),
        )

    async def _sync_device(self, device: dict[str, Any]) -> DeviceState:
        name = device.get("deviceName") or device["serialNumber"]
        state = DeviceState(device=device, folder=self.archive_dir / slugify(name))

        # First poll after startup backfills everything the cloud still has.
        start_ms = None
        if self._backfilled:
            start_ms = int((dt_util.utcnow() - LOOKBACK).timestamp() * 1000)
        events = await self.client.get_events(device, start_ms=start_ms)
        # Events not yet isReady may still lack their clip; the next poll gets them.
        ready = [ev for ev in events if ev.get("isReady")]
        visits = {ev["alarmId"]: self._visit(state.folder, ev) for ev in ready}

        def find_missing() -> list[dict[str, Any]]:
            return [
                ev for ev in ready
                if not (visits[ev["alarmId"]].has_video and visits[ev["alarmId"]].has_snapshot)
            ]

        missing = await self.hass.async_add_executor_job(find_missing)
        for i in range(0, len(missing), LINK_BATCH):
            batch = missing[i : i + LINK_BATCH]
            links = await self.client.get_download_links(device["serialNumber"], batch)
            for ev in batch:
                visit = visits[ev["alarmId"]]
                if await self._download(visit, links.get(ev["alarmId"], {})) and self._backfilled:
                    state.new_visits.append(visit)

        if ready:
            state.last_visit = visits[ready[0]["alarmId"]]
        state.new_visits.sort(key=lambda v: v.time)
        return state

    async def _download(self, visit: Visit, links: dict[str, str | None]) -> bool:
        """Fetch whichever files are missing; return True if anything was written."""
        wrote = False
        for path, url in ((visit.video, links.get("video")), (visit.snapshot, links.get("pic"))):
            if not url or await self.hass.async_add_executor_job(path.exists):
                continue
            try:
                data = await self.client.fetch_bytes(url)
            except NetvueError as err:
                _LOGGER.warning("Could not download %s: %s", path.name, err)
                continue
            await self.hass.async_add_executor_job(_write_atomic, path, data)
            wrote = True
        return wrote
