"""Fixtures: a fake Netvue cloud on top of aioclient_mock."""
from __future__ import annotations

import json

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.netvue_birdfy.api import DEVICES_URL, DOWNLOAD_LINK_URL, LOGIN_URL
from custom_components.netvue_birdfy.const import DOMAIN

SERIAL = "5000000000000001"
EVENTS_URL = f"https://eu-central-1-api2.nvts.co/devices/{SERIAL}/events"
DEVICE = {
    "serialNumber": SERIAL,
    "deviceName": "Voederkastje",
    "region": "eu-central-1",
    "productCode": "L14",
    "ethMacAddress": "b4:61:e9:00:00:01",
    "onAddx": True,
    "addxSn": "addx-sn-1",
}
ADDX_TOKEN_URL = "https://eu-central-1-api2.nvts.co/addx/token/v2"
ADDX_ATTRS_URL = "https://api-eu.example/device/getDeviceAttributes"
BIRD_COUNT_URL = "https://eu-central-1-api2.nvts.co/birdData/eventCount"
SPECIES_URL = "https://eu-central-1-api2.nvts.co/birdData/summary"
# 2026-10-06 16:41:25 and 13:43:04 Amsterdam time.
EVENT_NEW = "AAAnewest"
EVENT_OLD = "AAAolder"
EVENT_PENDING = "AAApending"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
async def media_dir(hass, tmp_path):
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    hass.config.media_dirs = {"local": str(tmp_path)}
    return tmp_path


def make_event(alarm_id: str, alert_ms: int, ready: bool = True) -> dict:
    return {
        "type": 56,
        "alarmId": alarm_id,
        "pic": f"bucket:owner/{SERIAL}/{alarm_id}/image.jpg",
        "isReady": ready,
        "status": 0,
        "description": json.dumps({"alarmId": alarm_id, "recordDir": f"bucket:owner/{SERIAL}/{alarm_id}"}),
        "alertTime": alert_ms,
        "aiRecognitionStatus": "auto_success",
    }


class FakeCloud:
    """Registers Netvue endpoints on aioclient_mock; tweak fields, then call install()."""

    def __init__(self, mock: AiohttpClientMocker) -> None:
        self.mock = mock
        self.login_response = {"ret": 0, "token": "tok-1", "userID": 1234567}
        self.devices_status = 200
        self.addx_result = 0
        self.realtime = {
            "online": 1,
            "batteryLevel": 87,
            "isCharging": 2,
            "chargingMode": 3,
            "signalStrength": -56,
            "firmwareId": "1.9.10",
            "sdCard": {"total": 59606, "used": 15341, "free": 44265},
        }
        self.bird_counts_status = 200
        self.events = [
            make_event(EVENT_NEW, 1791297685606),
            make_event(EVENT_OLD, 1791286984583),
        ]
        self.install()

    def install(self) -> None:
        self.mock.clear_requests()
        self.mock.post(LOGIN_URL, json=self.login_response)
        self.mock.get(DEVICES_URL, status=self.devices_status, json={"devices": [DEVICE]})
        self.mock.get(EVENTS_URL, json={"startKey": "", "events": self.events})
        self.mock.get(ADDX_TOKEN_URL, json={
            "token": "Bearer addx", "endpoint": "https://api-eu.example",
            "countryNo": "us", "language": "en",
        })
        self.mock.post(ADDX_ATTRS_URL, json={
            "result": self.addx_result, "msg": "Success",
            "data": {"realTimeAttributes": self.realtime},
        })
        self.mock.get(BIRD_COUNT_URL, status=self.bird_counts_status, json={"birdCountList": [
            {"tag": "AllBird", "group": 1, "count": 9},
            {"tag": "Dunnock", "group": 1, "count": 4},
            {"tag": "Great Tit", "group": 1, "count": 3},
            {"tag": "Bird", "group": 1, "count": 1},
            {"tag": "AllAnimal", "group": 2, "count": 2},
            {"tag": "Animal", "group": 2, "count": 2},
        ]})
        self.mock.get(SPECIES_URL, json={"total": 2, "birds": [
            {"createTime": 1779459266438, "birdName": "Black Redstart", "coverImageUrl": ""},
            {"createTime": 1773067649046, "birdName": "Dunnock", "coverImageUrl": ""},
        ]})
        self.mock.post(
            DOWNLOAD_LINK_URL,
            json={
                "ttl": 259200,
                "eventList": [
                    {
                        "alarmId": ev["alarmId"],
                        "videoFileList": [f"https://cdn.example/{ev['alarmId']}/output.mp4?jwt=x"],
                        "picList": [f"https://cdn.example/{ev['alarmId']}/image.jpg?jwt=x"],
                    }
                    for ev in self.events
                ],
            },
        )
        for ev in self.events:
            self.mock.get(f"https://cdn.example/{ev['alarmId']}/output.mp4?jwt=x", content=b"MP4" + ev["alarmId"].encode())
            self.mock.get(f"https://cdn.example/{ev['alarmId']}/image.jpg?jwt=x", content=b"\xff\xd8JPG" + ev["alarmId"].encode())

    def calls(self, url: str) -> int:
        return sum(1 for call in self.mock.mock_calls if str(call[1]).startswith(url))


@pytest.fixture
def cloud(aioclient_mock: AiohttpClientMocker) -> FakeCloud:
    return FakeCloud(aioclient_mock)


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="robin@example.com",
        unique_id="1234567",
        data={
            "email": "robin@example.com",
            "password_md5": "5f4dcc3b5aa765d61d8327deb882cf99",
            "udid": "android-test",
            "token": "tok-cached",
            "userid": "1234567",
        },
    )
