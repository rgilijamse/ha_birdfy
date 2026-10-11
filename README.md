# Netvue Birdfy for Home Assistant

Unofficial integration for Birdfy (Netvue) bird feeder cameras. It uses the
same reverse-engineered cloud API as the Birdfy Android app, so it can break
whenever Netvue changes that API.

The Birdfy cloud only keeps events for a few weeks. This integration copies
every clip (MP4) and snapshot (JPG) into Home Assistant's media folder, so you
keep them for as long as you like and can browse them in the Media Browser.

Birdfy feeders have no local stream (no RTSP/ONVIF), and the original Feeder
cannot push RTMP either, so live view is out of scope.

## Status

Early development, tested against one original Birdfy Feeder (product code
`L14`) on the `eu-central-1` region.

- [x] Archive clips and snapshots, entities for the latest visit
- [x] Battery, signal, SD card, online (Addx/VicoHome API, `onAddx` devices only)
- [x] Species counts and the account's species list
- [x] Species per clip (bird search per species tag)
- [x] Charging and solar power (`isCharging` / `chargingMode` codes)
- [x] Gallery (Advanced Camera Card, see below)
- [ ] Optional retention / cleanup

## What you get

Per feeder:

| Entity | What it is |
|---|---|
| `sensor.<feeder>_last_visit` | Time of the newest event; attributes `species`, `detected` (`bird`/`animal`), and `video`/`snapshot` as `media-source://` URIs |
| `image.<feeder>_last_snapshot` | Snapshot of the newest event, served from the local copy |
| `event.<feeder>_visit` | Fires once for every new event (not for the backfill after a restart), with the same attributes |
| `sensor.<feeder>_battery` | Battery %; `charging_state` (`none`/`charging`/`full`) and the raw `charging_mode` code as attributes |
| `binary_sensor.<feeder>_charging` | On while the battery is charging (off when full or without power in) |
| `binary_sensor.<feeder>_solar_power` | On while the solar panel supplies power |
| `sensor.<feeder>_signal_strength` | WiFi signal in dBm (diagnostic) |
| `sensor.<feeder>_sd_card_free` | Free space on the SD card (diagnostic); total and used as attributes |
| `binary_sensor.<feeder>_online` | Whether the cloud sees the feeder as connected (diagnostic) |
| `sensor.<feeder>_recent_species` | Number of species among the events the cloud still holds; `counts` per species |
| `sensor.<feeder>_species_seen` | Species ever recorded on the account; `species` list with first-seen dates |

The charging codes were worked out against a weather station's solar radiation
sensor next to the panel: `chargingMode` is 3 while the panel supplies power and
0 without (it switches at twilight, around 1–6 W/m²); `isCharging` is 0 without
power in, 1 while charging and 2 when full. With a panel the battery sits at
100% and only tops up now and then. USB power has not been tried, so its
`chargingMode` code is unknown (`solar_power` likely turns on for it too).

Battery, signal, SD card and online come from the Addx (VicoHome) platform and
only exist for feeders that report `onAddx`. If one of these extra calls fails,
its entities go unavailable but archiving carries on.

The species of a clip comes from the cloud AI, which can lag behind the clip.
A visit event may then fire with `species: null`; `last_visit` picks the
species up on a later poll. Species are searched for again only when the
species counts change, so this costs one call per species, not per poll.

Files are stored as `<media>/<folder>/<feeder>/YYYY-MM-DD/HHMMSS_<alarmId>.{mp4,jpg}`,
using Home Assistant's local time. `<folder>` is set during setup (default
`netvue_birdfy`) and can be changed under Configure. Network storage added to
Home Assistant for media is mounted inside the media folder, so a share named
`cctv` is used with a folder like `cctv/birdfy`. Changing the folder does not
move existing files. A file on disk is the record that an event
was archived; there is no other state. Nothing is deleted automatically.

The integration polls every 5 minutes and looks back 3 days (how long the
download links stay valid), so missed or failed downloads are retried. The
first poll after a restart backfills everything the cloud still has.

It adds no HTTP endpoints to Home Assistant; all media goes through the
normal, authenticated media source.

## Setup

Install with HACS (custom repository, category Integration), or copy
`custom_components/netvue_birdfy` into your `config/custom_components`.
Restart Home Assistant, then add **Netvue Birdfy** under Settings → Devices &
services and log in with your Birdfy account.

Only an MD5 hash of the password is stored, because that is what the Netvue
login sends. It still works as a password for your Birdfy account. Each login
triggers a "New Login to Your Birdfy Account" email; the phone app stays
logged in. The session token is kept, so that only happens when it expires.

## Automation example

```yaml
triggers:
  - trigger: state
    entity_id: event.voederkastje_visit
actions:
  - action: notify.mobile_app_phone
    data:
      message: Visitor at the feeder
      data:
        # Companion app wants a /media/local/... path
        image: >-
          {{ trigger.to_state.attributes.snapshot
             | replace('media-source://media_source/local/', '/media/local/') }}
```

## Gallery

[Advanced Camera Card](https://github.com/dermotduffy/advanced-camera-card)
(HACS) can show the archive as a gallery without a camera entity. One tile
per clip, with the snapshot as its thumbnail, sorted by date and time:

```yaml
type: custom:advanced-camera-card
view:
  default: folders
folders:
  - type: ha
    title: Voederkastje
    ha:
      path:
        - id: media-source://media_source/local/cctv/voederkastje  # <folder>/<feeder>
        - parsers:
            - type: date
              format: yyyy-MM-dd
        - matchers:
            - type: title
              regexp: \.mp4$
          parsers:
            - type: date
              regexp: ^\d{6}
              format: HHmmss
            - type: thumbnail  # pairs x.mp4 with x.jpg
```

## Development

Tests and the CLI run in a container, so nothing gets installed on the host.
The image pins `pytest-homeassistant-custom-component`, which pins the Home
Assistant version (currently 2026.9.4).

```sh
podman build -t ha-birdfy-test -f tools/Containerfile tools/
podman run --rm -v "$PWD":/src:ro ha-birdfy-test pytest
```

`tools/birdfy_cli.py` makes signed requests to the API for exploring it.
Credentials live in `~/.config/birdfy/` (mode 600: email, password hash,
client id, cached token):

```sh
podman run --rm -it -v "$PWD":/src:ro -v ~/.config/birdfy:/root/.config/birdfy \
    ha-birdfy-test python tools/birdfy_cli.py setup
podman run --rm -v "$PWD":/src:ro -v ~/.config/birdfy:/root/.config/birdfy \
    ha-birdfy-test python tools/birdfy_cli.py events 5
```

### Layout

| Path | |
|---|---|
| `custom_components/netvue_birdfy/api.py` | Async API client, no Home Assistant imports (the CLI loads it directly) |
| `custom_components/netvue_birdfy/coordinator.py` | Polling and downloading |
| `tests/` | Integration tests against a fake Netvue cloud |
| `tools/` | Containerfile and CLI |

### API notes

| Call | |
|---|---|
| `POST localweb.nvts.co/v1/users/login/v2` | `{username, password: md5, locale}` → `token`, `userID` |
| `GET localweb.nvts.co/v1/devices/v3` | Devices: `serialNumber`, `deviceName`, `region`, `productCode` |
| `GET {region}-api2.nvts.co/devices/{sn}/events` | `limit`, `reverse=1`, `startTime`/`endTime` (ms), paged with `startKey` |
| `POST localapi2.nvts.co/event/downloadLink` | Pre-signed MP4 and JPG URLs per `alarmId`, valid for 3 days |
| `GET {region}-api2.nvts.co/birdData/eventCount?serialnumber=` | Counts per species tag (`AllBird`/`Bird`/`Animal` are totals or unidentified) |
| `GET {region}-api2.nvts.co/birdData/summary?pageSize=` | Species ever recorded on the account |
| `GET centralapi.nvts.co/v2/birddata/search` | `serialnumber`, `startTime`/`endTime` (ms, at most 30 days), `pageSize` (at most 20), `tag` (species), paged with `nextStartKey`/`startKey` → events with that species. Without `tag`: events with no species |
| `GET {region}-api2.nvts.co/addx/token/v2?region=` | Addx bearer token and API endpoint (e.g. `https://api-eu.vicohome.io`) |
| `POST <addx endpoint>/device/getDeviceAttributes` | `{serialNumber: addxSn, returnRealTimeAttributes: true}` → battery, signal, SD card |

Event `labelMask` bits: 32 = bird, 16 = animal. `/birdData/logSummary`
(`group=day|week`, `timezone`) came back empty for this feeder.

Devices with `onAddx` do not use the AWS IoT shadow, even though
`v1/sts/client?type=1&area=global&groupId=` hands out credentials for it.

Signed requests use HMAC-SHA256 headers (`x-nvs-signature`, `x-nvs-time`,
`x-nvs-ucid`, `x-nvs-udid`, `x-nvs-userid`); see `api.py`.

## Credits

Login and request signing are based on
[sebsst/birdfy-integration](https://github.com/sebsst/birdfy-integration) (MIT).
