"""Config flow for Netvue Birdfy."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import NetvueAuthError, NetvueClient, NetvueError, hash_password, new_udid
from .const import CONF_PASSWORD_MD5, CONF_UDID, CONF_USERID, DOMAIN

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class BirdfyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Log in with a Birdfy account; only the md5 of the password is stored."""

    VERSION = 1

    async def _login(self, email: str, password_md5: str, udid: str) -> NetvueClient:
        client = NetvueClient(async_get_clientsession(self.hass), email, password_md5, udid)
        await client.login()
        return client

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password_md5 = hash_password(user_input[CONF_PASSWORD])
            udid = new_udid()
            try:
                client = await self._login(email, password_md5, udid)
            except NetvueAuthError:
                errors["base"] = "invalid_auth"
            except NetvueError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(client.userid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=email,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD_MD5: password_md5,
                        CONF_UDID: udid,
                        CONF_TOKEN: client.token,
                        CONF_USERID: client.userid,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password_md5 = hash_password(user_input[CONF_PASSWORD])
            try:
                client = await self._login(
                    entry.data[CONF_EMAIL], password_md5, entry.data[CONF_UDID]
                )
            except NetvueAuthError:
                errors["base"] = "invalid_auth"
            except NetvueError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_PASSWORD_MD5: password_md5,
                        CONF_TOKEN: client.token,
                        CONF_USERID: client.userid,
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )
