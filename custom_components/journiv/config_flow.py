"""Config flow for the Journiv integration."""

from collections.abc import Mapping
import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow as ConfigFlowBase,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import (
    JournivApi,
    JournivAuthenticationError,
    JournivConnectionError,
    JournivJournal,
    normalize_host,
)
from .const import CONF_JOURNAL_IDS, CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

DESCRIPTION_PLACEHOLDERS = {
    "example_url": "https://journiv.example.com:8443",
    "http_scheme": "http://",
    "https_scheme": "https://",
}


STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): str,
        probatio.Required(CONF_EMAIL): str,
        probatio.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""

    if (host := normalize_host(data[CONF_HOST])) is None:
        raise InvalidHost

    normalized_data = {**data, CONF_HOST: host}
    session = async_get_clientsession(hass)

    api = JournivApi(
        session=session,
        host=host,
    )

    try:
        await api.authenticate(
            email=normalized_data[CONF_EMAIL],
            password=normalized_data[CONF_PASSWORD],
        )

        user = await api.get_current_user()

    except JournivAuthenticationError as err:
        raise InvalidAuth from err

    except JournivConnectionError as err:
        raise CannotConnect from err

    return {
        "api": api,
        "title": user.get("email", "Journiv"),
        "user_id": user["id"],
        "data": normalized_data,
    }


def _entry_unique_id(host: str, user_id: str) -> str:
    """Return an identifier unique across Journiv installations."""
    return f"{host}#{user_id}"


def _entry_data(data: Mapping[str, Any], refresh_token: str | None) -> dict[str, Any]:
    """Return config entry data with the minimum required credentials."""
    if refresh_token:
        return {
            CONF_HOST: data[CONF_HOST],
            CONF_EMAIL: data[CONF_EMAIL],
            CONF_REFRESH_TOKEN: refresh_token,
        }
    return {
        CONF_HOST: data[CONF_HOST],
        CONF_EMAIL: data[CONF_EMAIL],
        CONF_PASSWORD: data[CONF_PASSWORD],
    }


class ConfigFlow(ConfigFlowBase, domain=DOMAIN):
    """Handle a config flow for Journiv."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._journals: list[JournivJournal] = []
        self._refresh_token: str | None = None
        self._title = ""
        self._user_input: dict[str, Any] = {}

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> JournivOptionsFlow:
        """Return the options flow handler."""
        return JournivOptionsFlow()

    @override
    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(
                    self.hass,
                    user_input,
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"

            except InvalidAuth:
                errors["base"] = "invalid_auth"

            except InvalidHost:
                errors["base"] = "invalid_url"

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            else:
                await self.async_set_unique_id(
                    _entry_unique_id(info["data"][CONF_HOST], info["user_id"])
                )

                self._abort_if_unique_id_configured()

                try:
                    self._journals = await info["api"].get_journals()
                except JournivAuthenticationError:
                    errors["base"] = "invalid_auth"
                except JournivConnectionError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception fetching journals")
                    errors["base"] = "unknown"
                else:
                    self._title = info["title"]
                    self._refresh_token = info["api"].refresh_token
                    self._user_input = info["data"]
                    return await self.async_step_journals()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=DESCRIPTION_PLACEHOLDERS,
        )

    async def async_step_journals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user select journals to monitor."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._title,
                data=_entry_data(self._user_input, self._refresh_token),
                options={CONF_JOURNAL_IDS: user_input[CONF_JOURNAL_IDS]},
            )

        return self.async_show_form(
            step_id="journals",
            data_schema=_journals_schema(
                self._journals,
                [journal["id"] for journal in self._journals],
            ),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle initiation of reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {CONF_HOST: reauth_entry.data[CONF_HOST], **user_input}
            try:
                info = await validate_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidHost:
                errors["base"] = "invalid_url"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                unique_id = _entry_unique_id(info["data"][CONF_HOST], info["user_id"])
                await self.async_set_unique_id(unique_id, raise_on_progress=False)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    unique_id=unique_id,
                    title=info["title"],
                    data=_entry_data(info["data"], info["api"].refresh_token),
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_EMAIL, default=reauth_entry.data[CONF_EMAIL]
                    ): str,
                    probatio.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={"host": reauth_entry.data[CONF_HOST]},
        )


class JournivOptionsFlow(OptionsFlowWithReload):
    """Handle Journiv options."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._journals: list[JournivJournal] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user update the monitored journals."""
        if user_input is not None and self._journals is not None:
            return self.async_create_entry(data=user_input)

        errors: dict[str, str] = {}
        api = JournivApi(
            session=async_get_clientsession(self.hass),
            host=self.config_entry.data[CONF_HOST],
        )
        try:
            if refresh_token := self.config_entry.data.get(CONF_REFRESH_TOKEN):
                await api.refresh_access_token(refresh_token)
            else:
                await api.authenticate(
                    email=self.config_entry.data[CONF_EMAIL],
                    password=self.config_entry.data[CONF_PASSWORD],
                )
            self._journals = await api.get_journals()
        except JournivAuthenticationError:
            errors["base"] = "invalid_auth"
        except JournivConnectionError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception fetching journals")
            errors["base"] = "unknown"

        if api.refresh_token and api.refresh_token != self.config_entry.data.get(
            CONF_REFRESH_TOKEN
        ):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    CONF_HOST: self.config_entry.data[CONF_HOST],
                    CONF_EMAIL: self.config_entry.data[CONF_EMAIL],
                    CONF_REFRESH_TOKEN: api.refresh_token,
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_journals_schema(
                self._journals or [],
                (
                    self.config_entry.options.get(CONF_JOURNAL_IDS, [])
                    if self._journals is not None
                    else []
                ),
            ),
            errors=errors,
        )


def _journals_schema(
    journals: list[JournivJournal], selected_journal_ids: list[str]
) -> probatio.Schema:
    """Build a schema for selecting journals."""
    return probatio.Schema(
        {
            probatio.Required(
                CONF_JOURNAL_IDS, default=selected_journal_ids
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=journal["id"], label=journal["title"])
                        for journal in journals
                    ],
                    multiple=True,
                    sort=True,
                )
            )
        }
    )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class InvalidHost(Exception):
    """Error to indicate the host URL is invalid."""
