"""Setup, archiving and entity tests."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState, SOURCE_REAUTH
from homeassistant.core import HomeAssistant
import pytest

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import EVENT_NEW, EVENT_OLD, EVENT_PENDING, make_event


async def setup(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_backfill_writes_files(hass, entry, cloud, media_dir) -> None:
    cloud.events.append(make_event(EVENT_PENDING, 1791297700000, ready=False))
    cloud.install()
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    day = media_dir / "netvue_birdfy" / "voederkastje" / "2026-10-06"
    assert sorted(p.name for p in day.iterdir()) == [
        f"134304_{EVENT_OLD}.jpg",
        f"134304_{EVENT_OLD}.mp4",
        f"164125_{EVENT_NEW}.jpg",
        f"164125_{EVENT_NEW}.mp4",
    ]
    assert (day / f"164125_{EVENT_NEW}.mp4").read_bytes() == b"MP4" + EVENT_NEW.encode()
    assert not list(media_dir.rglob("*.part"))

    # Cached token reused: no login call.
    assert cloud.calls("https://localweb.nvts.co/v1/users/login") == 0


async def test_entities(hass, entry, cloud) -> None:
    await setup(hass, entry)
    ent_reg = er.async_get(hass)
    ids = {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)}
    sensor = hass.states.get(ids["5000000000000001_last_visit"])
    assert sensor.state == "2026-10-06T14:41:25+00:00"
    assert sensor.attributes["video"] == (
        f"media-source://media_source/local/netvue_birdfy/voederkastje/2026-10-06/164125_{EVENT_NEW}.mp4"
    )

    image = hass.states.get(ids["5000000000000001_last_snapshot"])
    assert dt_util.parse_datetime(image.state) == dt_util.parse_datetime("2026-10-06T14:41:25.606+00:00")

    # Backfill must not fire visit events.
    event = hass.states.get(ids["5000000000000001_visit"])
    assert event.state == "unknown"


async def test_image_served_from_disk(hass, entry, cloud, hass_client) -> None:
    await setup(hass, entry)
    ent_reg = er.async_get(hass)
    image_id = ent_reg.async_get_entity_id("image", "netvue_birdfy", "5000000000000001_last_snapshot")
    client = await hass_client()
    resp = await client.get(f"/api/image_proxy/{image_id}")
    assert resp.status == 200
    assert await resp.read() == b"\xff\xd8JPG" + EVENT_NEW.encode()


async def test_new_event_fires_once(hass, entry, cloud, media_dir) -> None:
    await setup(hass, entry)
    coordinator = entry.runtime_data
    ent_reg = er.async_get(hass)
    event_id = ent_reg.async_get_entity_id("event", "netvue_birdfy", "5000000000000001_visit")

    cloud.events.insert(0, make_event("AAAfresh", 1791300000000))
    cloud.install()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(event_id)
    assert state.attributes["event_type"] == "visit"
    assert state.attributes["alarm_id"] == "AAAfresh"
    fired_at = state.state

    # Next poll: nothing new to download, so no new event.
    cloud.install()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(event_id).state == fired_at
    assert cloud.calls("https://localapi2.nvts.co/event/downloadLink") == 0


async def test_expired_token_relogs_and_persists(hass, entry, cloud) -> None:
    cloud.devices_status = 401
    cloud.install()
    entry.add_to_hass(hass)
    # Every devices call returns 401, so setup fails, but the re-login must
    # have happened and the new token must be saved on the entry.
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert cloud.calls("https://localweb.nvts.co/v1/users/login") == 1
    assert entry.data["token"] == "tok-1"


async def test_rejected_credentials_start_reauth(hass, entry, cloud) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, "token": None})
    cloud.login_response = {"ret": 2, "msg": "wrong password"}
    cloud.install()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


def _state(hass, key: str, domain: str = "sensor"):
    entity_id = er.async_get(hass).async_get_entity_id(domain, "netvue_birdfy", f"5000000000000001_{key}")
    return hass.states.get(entity_id)


async def test_addx_and_species_sensors(hass, entry, cloud) -> None:
    await setup(hass, entry)
    battery = _state(hass, "battery")
    assert battery.state == "87"
    assert battery.attributes["is_charging"] == 2
    assert _state(hass, "signal_strength").state == "-56"
    sd = _state(hass, "sd_card_free")
    assert float(sd.state) == pytest.approx(44.265)  # MB shown as GB
    assert _state(hass, "online", "binary_sensor").state == "on"

    recent = _state(hass, "recent_species")
    assert recent.state == "2"
    assert recent.attributes["counts"] == {"Dunnock": 4, "Great Tit": 3}
    seen = _state(hass, "species_seen")
    assert seen.state == "2"
    assert [s["name"] for s in seen.attributes["species"]] == ["Black Redstart", "Dunnock"]

    device_id = er.async_get(hass).async_get(battery.entity_id).device_id
    device = dr.async_get(hass).async_get(device_id)
    assert device.sw_version == "1.9.10"


async def test_extras_failing_do_not_break_archiving(hass, entry, cloud, media_dir) -> None:
    cloud.addx_result = 5
    cloud.bird_counts_status = 500
    cloud.install()
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert _state(hass, "battery").state == "unavailable"
    assert _state(hass, "recent_species").state == "unavailable"
    assert _state(hass, "online", "binary_sensor").state == "unavailable"
    assert _state(hass, "species_seen").state == "2"
    assert list(media_dir.rglob("*.mp4"))
