#!/usr/bin/env python3
"""Command-line access to the Netvue API, for testing and reverse engineering.

  tools/birdfy_cli.py setup             # store email + md5(password) once
  tools/birdfy_cli.py devices           # raw device list
  tools/birdfy_cli.py events [N]        # newest N events (follows paging)
  tools/birdfy_cli.py links [N]         # download links for the newest N events
  tools/birdfy_cli.py raw GET <url>     # signed request to any endpoint
  tools/birdfy_cli.py raw POST <url> <json>

Credentials and the cached session token live in ~/.config/birdfy/ (mode 600).
Run it in the test container (see tools/Containerfile) with ~/.config/birdfy mounted.
"""
import asyncio
import getpass
import importlib.util
import json
import os
from pathlib import Path
import sys

import aiohttp

# Load api.py by path: importing the package would pull in Home Assistant.
_API_PATH = Path(__file__).resolve().parent.parent / "custom_components" / "netvue_birdfy" / "api.py"
_spec = importlib.util.spec_from_file_location("netvue_api", _API_PATH)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)

CONF_DIR = Path.home() / ".config" / "birdfy"
CRED_FILE = CONF_DIR / "credentials.json"
TOKEN_FILE = CONF_DIR / "session.json"


def write_private(path: Path, data: dict) -> None:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONF_DIR, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)


def load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def setup() -> None:
    email = input("Birdfy email: ").strip()
    pwd_md5 = api.hash_password(getpass.getpass("Birdfy password: "))
    udid = load(CRED_FILE).get("udid") or api.new_udid()
    write_private(CRED_FILE, {"email": email, "password_md5": pwd_md5, "udid": udid})
    TOKEN_FILE.unlink(missing_ok=True)
    print(f"Saved to {CRED_FILE}")


def dump(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


async def run(cmd: str, args: list[str]) -> None:
    cred = load(CRED_FILE)
    if not cred:
        sys.exit("Run 'setup' first")
    sess = load(TOKEN_FILE)
    async with aiohttp.ClientSession() as session:
        client = api.NetvueClient(
            session, cred["email"], cred["password_md5"], cred["udid"],
            token=sess.get("token"), userid=sess.get("userid"),
            on_token=lambda t, u: write_private(TOKEN_FILE, {"token": t, "userid": u}),
        )
        devices = await client.get_devices()
        if cmd == "devices":
            return dump(devices)
        if cmd == "raw":
            body = {"json": json.loads(args[2])} if len(args) > 2 else {}
            return dump(await client._request(args[0], args[1], **body))
        device = devices[0]
        n = int(args[0]) if args else 10
        events = (await client.get_events(device, page_size=min(n, 50)))[:n]
        if cmd == "events":
            return dump(events)
        if cmd == "links":
            return dump(await client.get_download_links(device["serialNumber"], events))
        sys.exit(__doc__)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "setup":
        setup()
    else:
        asyncio.run(run(sys.argv[1], sys.argv[2:]))
