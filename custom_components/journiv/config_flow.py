"""Config flow for the Journiv integration."""

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

    session = async_get_clientsession(hass)

    api = JournivApi(
        session=session,
        host=data[CONF_HOST],
    )

    try:
        await api.authenticate(
            email=data[CONF_EMAIL],
            password=data[CONF_PASSWORD],
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
    }


class ConfigFlow(ConfigFlowBase, domain=DOMAIN):
    """Handle a config flow for Journiv."""

    VERSION = 1

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

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            else:
                await self.async_set_unique_id(info["user_id"])

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
                    self._user_input = user_input
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
            data = self._user_input
            if refresh_token := self._refresh_token:
                data = {**data, CONF_REFRESH_TOKEN: refresh_token}
            return self.async_create_entry(
                title=self._title,
                data=data,
                options={CONF_JOURNAL_IDS: user_input[CONF_JOURNAL_IDS]},
            )

        return self.async_show_form(
            step_id="journals",
            data_schema=_journals_schema(
                self._journals,
                [journal["id"] for journal in self._journals],
            ),
        )


class JournivOptionsFlow(OptionsFlowWithReload):
    """Handle Journiv options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user update the monitored journals."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        api = JournivApi(
            session=async_get_clientsession(self.hass),
            host=self.config_entry.data[CONF_HOST],
        )
        try:
            if refresh_token := self.config_entry.data.get(CONF_REFRESH_TOKEN):
                try:
                    await api.refresh_access_token(refresh_token)
                except JournivAuthenticationError:
                    await api.authenticate(
                        email=self.config_entry.data[CONF_EMAIL],
                        password=self.config_entry.data[CONF_PASSWORD],
                    )
            else:
                await api.authenticate(
                    email=self.config_entry.data[CONF_EMAIL],
                    password=self.config_entry.data[CONF_PASSWORD],
                )
            journals = await api.get_journals()
        except JournivAuthenticationError:
            return self.async_abort(reason="invalid_auth")
        except JournivConnectionError:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception("Unexpected exception fetching journals")
            return self.async_abort(reason="unknown")

        if api.refresh_token and api.refresh_token != self.config_entry.data.get(
            CONF_REFRESH_TOKEN
        ):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_REFRESH_TOKEN: api.refresh_token,
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=_journals_schema(
                journals,
                self.config_entry.options.get(CONF_JOURNAL_IDS, []),
            ),
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
