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
- [ ] Species names (the AI result is not in the event list; endpoint unknown)
- [ ] Battery level (not in the device list; likely AWS IoT shadow or Addx API)
- [ ] Snapshot gallery card
- [ ] Optional retention / cleanup

## What you get

Per feeder:

| Entity | What it is |
|---|---|
| `sensor.<feeder>_last_visit` | Time of the newest event; attributes `video` and `snapshot` are `media-source://` URIs |
| `image.<feeder>_last_snapshot` | Snapshot of the newest event, served from the local copy |
| `event.<feeder>_visit` | Fires once for every new event (not for the backfill after a restart) |

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

Signed requests use HMAC-SHA256 headers (`x-nvs-signature`, `x-nvs-time`,
`x-nvs-ucid`, `x-nvs-udid`, `x-nvs-userid`); see `api.py`.

## Credits

Login and request signing are based on
[sebsst/birdfy-integration](https://github.com/sebsst/birdfy-integration) (MIT).
