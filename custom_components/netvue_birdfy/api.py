"""Async client for the Netvue cloud API used by Birdfy feeders.

Deliberately free of Home Assistant imports so tools/ can use it from the CLI.
Request signing, login and the UCID come from sebsst/birdfy-integration (MIT).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
import hashlib
import hmac
import json
import time
from typing import Any
import uuid

import aiohttp

UCID = "b3cf543b57"
USER_AGENT = "Birdfy/1.19.2 (build 123960) NetvueSDK/1.6.1 Android/12"
LOGIN_URL = "https://localweb.nvts.co/v1/users/login/v2"
DEVICES_URL = "https://localweb.nvts.co/v1/devices/v3"
DOWNLOAD_LINK_URL = "https://localapi2.nvts.co/event/downloadLink"
DEFAULT_REGION = "eu-central-1"
EVENT_TYPE_MOTION = 56
TIMEOUT = aiohttp.ClientTimeout(total=60)


class NetvueError(Exception):
    """Unexpected API response or transport failure."""


class NetvueAuthError(NetvueError):
    """Credentials were rejected."""


def hash_password(password: str) -> str:
    """Return the md5 hex digest the login endpoint expects."""
    return hashlib.md5(password.encode()).hexdigest()


def new_udid() -> str:
    """Return a fresh client device id, as the Android app generates one."""
    return f"android-{uuid.uuid4()}"


def _hmac(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


class NetvueClient:
    """Netvue account session; logs in again once when the token is rejected."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password_md5: str,
        udid: str,
        token: str | None = None,
        userid: str | None = None,
        on_token: Callable[[str, str], None] | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password_md5 = password_md5
        self._udid = udid
        self.token = token
        self.userid = userid
        self._on_token = on_token

    async def login(self) -> None:
        """Log in and store a new session token."""
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "x-nvs-ucid": UCID,
            "x-nvs-udid": self._udid,
        }
        payload = {"username": self._email, "password": self._password_md5, "locale": "en-US"}
        try:
            async with self._session.post(
                LOGIN_URL, json=payload, headers=headers, timeout=TIMEOUT
            ) as resp:
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise NetvueError(f"Login request failed: {err}") from err
        if data.get("ret", 0) != 0 or not data.get("token"):
            raise NetvueAuthError(f"Login rejected: ret={data.get('ret')} msg={data.get('msg')}")
        self.token = data["token"]
        self.userid = str(data["userID"])
        if self._on_token:
            self._on_token(self.token, self.userid)

    def _auth_headers(self) -> dict[str, str]:
        ts = str(int(time.time() * 1000))
        key = "nvs1" + self.token
        for msg in (UCID, self._udid, self.userid, ts):
            key = _hmac(key, msg)
        return {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "x-nvs-signature": _hmac(key, "nvs1_request"),
            "x-nvs-time": ts,
            "x-nvs-ucid": UCID,
            "x-nvs-udid": self._udid,
            "x-nvs-userid": self.userid,
            "x-nvs-version": '{"signature":2}',
        }

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if not self.token:
            await self.login()
        for attempt in range(2):
            try:
                async with self._session.request(
                    method, url, headers=self._auth_headers(), timeout=TIMEOUT, **kwargs
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        await self.login()
                        continue
                    if resp.status != 200:
                        text = await resp.text()
                        raise NetvueError(f"{method} {url}: HTTP {resp.status} {text[:200]}")
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise NetvueError(f"{method} {url}: {err}") from err
        raise NetvueAuthError("Session token rejected right after login")

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return the account's devices."""
        data = await self._request("GET", DEVICES_URL)
        return data.get("devices", data.get("deviceList", []))

    async def get_events(
        self,
        device: dict[str, Any],
        start_ms: int | None = None,
        end_ms: int | None = None,
        page_size: int = 50,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """Return motion events, newest first, following startKey paging."""
        region = device.get("region") or DEFAULT_REGION
        url = f"https://{region}-api2.nvts.co/devices/{device['serialNumber']}/events"
        params: dict[str, Any] = {"limit": page_size, "ignoreAiLabels": "false", "reverse": 1}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        events: list[dict[str, Any]] = []
        for _ in range(max_pages):
            data = await self._request("GET", url, params=params)
            events.extend(data.get("events", []))
            start_key = data.get("startKey")
            if not start_key or start_key == params.get("startKey"):
                break
            params["startKey"] = start_key
        return events

    async def get_download_links(
        self, serial: str, events: Iterable[dict[str, Any]]
    ) -> dict[str, dict[str, str | None]]:
        """Return {alarmId: {"video": url, "pic": url}} with links valid for days."""
        event_list = []
        for ev in events:
            entry: dict[str, Any] = {
                "serialnumber": serial,
                "alarmId": ev["alarmId"],
                "dataGroup": ["video", "pic"],
                "type": ev.get("type", EVENT_TYPE_MOTION),
            }
            record_dir = record_dir_of(ev)
            if record_dir:
                entry["recordDir"] = record_dir
            if ev.get("pic"):
                entry["pic"] = ev["pic"]
            event_list.append(entry)
        if not event_list:
            return {}
        data = await self._request("POST", DOWNLOAD_LINK_URL, json={"eventList": event_list})
        return {
            item["alarmId"]: {
                "video": next(iter(item.get("videoFileList") or []), None),
                "pic": next(iter(item.get("picList") or []), None),
            }
            for item in data.get("eventList", [])
            if item.get("alarmId")
        }

    async def fetch_bytes(self, url: str) -> bytes:
        """Download a pre-signed media URL (no auth headers)."""
        try:
            async with self._session.get(url, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    raise NetvueError(f"Download failed: HTTP {resp.status}")
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NetvueError(f"Download failed: {err}") from err


def record_dir_of(event: dict[str, Any]) -> str | None:
    """Return the recordDir hidden in an event's JSON description."""
    try:
        return json.loads(event.get("description") or "{}").get("recordDir")
    except ValueError:
        return None
