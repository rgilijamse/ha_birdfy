"""Config flow tests."""
from __future__ import annotations

import hashlib

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.netvue_birdfy.const import DOMAIN

USER_INPUT = {"email": " robin@example.com ", "password": "password"}


async def test_user_flow_stores_hash_only(hass, cloud) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert "password" not in data
    assert data["email"] == "robin@example.com"
    assert data["password_md5"] == "5f4dcc3b5aa765d61d8327deb882cf99"
    assert data["token"] == "tok-1"
    assert data["udid"].startswith("android-")
    assert result["result"].unique_id == "1234567"


async def test_user_flow_invalid_auth(hass, cloud) -> None:
    cloud.login_response = {"ret": 2, "msg": "wrong password"}
    cloud.install()
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reauth_updates_hash(hass, entry, cloud) -> None:
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password_md5"] == hashlib.md5(b"new-password").hexdigest()
    assert entry.data["token"] == "tok-1"
