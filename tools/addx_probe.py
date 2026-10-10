#!/usr/bin/env python3
"""Call the Addx (VicoHome) API that Netvue uses for newer feeders (onAddx=true).

  tools/addx_probe.py <path> [json-body]
  tools/addx_probe.py device/getDeviceAttributes      # default body for the first device

Flow, from the Birdfy app (1.23.0): GET {region}-api2.nvts.co/addx/token/v2?region=<region>
returns {token: "Bearer ...", endpoint: "https://api-eu.vicohome.io", ...}; Addx calls
are then POSTs to <endpoint>/<path> with that Authorization header.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys

import aiohttp

_CLI_PATH = Path(__file__).resolve().parent / "birdfy_cli.py"
_spec = importlib.util.spec_from_file_location("birdfy_cli", _CLI_PATH)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


async def main(path: str, body: dict | None) -> None:
    cred = cli.load(cli.CRED_FILE)
    sess = cli.load(cli.TOKEN_FILE)
    async with aiohttp.ClientSession() as session:
        client = cli.api.NetvueClient(
            session, cred["email"], cred["password_md5"], cred["udid"],
            token=sess.get("token"), userid=sess.get("userid"),
            on_token=lambda t, u: cli.write_private(cli.TOKEN_FILE, {"token": t, "userid": u}),
        )
        device = (await client.get_devices())[0]
        region = device.get("region") or "eu-central-1"
        addx = await client._request("GET", f"https://{region}-api2.nvts.co/addx/token/v2?region={region}")
        if body is None:
            body = {
                "serialNumber": device["addxSn"],
                "returnFixedAttributes": True,
                "returnModifiableAttributes": True,
                "returnRealTimeAttributes": True,
            }
        body.setdefault("countryNo", addx.get("countryNo"))
        body.setdefault("language", addx.get("language"))
        async with session.post(
            f"{addx['endpoint']}/{path}", json=body,
            headers={"Authorization": addx["token"], "Content-Type": "application/json"},
        ) as resp:
            print(f"HTTP {resp.status}", file=sys.stderr)
            text = await resp.text()
        try:
            print(json.dumps(json.loads(text), indent=2, ensure_ascii=False))
        except ValueError:
            print(text)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "device/getDeviceAttributes",
                     json.loads(sys.argv[2]) if len(sys.argv) > 2 else None))
