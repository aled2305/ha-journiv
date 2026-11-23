"""Data update coordinator for Journiv."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import override

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    JournivApi,
    JournivAuthenticationError,
    JournivConnectionError,
    JournivJournal,
    JournivMoodStatistics,
    JournivMoodStreak,
    JournivUser,
    JournivWritingAnalytics,
)
from .const import CONF_REFRESH_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

type JournivConfigEntry = ConfigEntry[JournivDataUpdateCoordinator]


@dataclass
class JournivData:
    """Data returned by Journiv."""

    journals: dict[str, JournivJournal]
    writing: JournivWritingAnalytics
    mood_statistics: JournivMoodStatistics
    mood_streak: JournivMoodStreak
    user: JournivUser


class JournivDataUpdateCoordinator(DataUpdateCoordinator[JournivData]):
    """Coordinate updates from Journiv."""

    config_entry: JournivConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: JournivConfigEntry,
        api: JournivApi,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.api = api

    @override
    async def _async_update_data(self) -> JournivData:
        """Fetch journals from Journiv."""
        try:
            if not self.api.access_token:
                await self._async_authenticate()
            try:
                data = await self._async_fetch_data()
            except JournivAuthenticationError:
                await self._async_authenticate()
                data = await self._async_fetch_data()
        except JournivAuthenticationError as err:
            raise ConfigEntryAuthFailed("Journiv authentication failed") from err
        except JournivConnectionError as err:
            raise UpdateFailed("Unable to update Journiv data") from err

        if (
            self.api.refresh_token
            and self.api.refresh_token != self.config_entry.data.get(CONF_REFRESH_TOKEN)
        ):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_REFRESH_TOKEN: self.api.refresh_token,
                },
            )

        return data

    async def _async_fetch_data(self) -> JournivData:
        """Fetch journal and account statistics."""
        journals = await self.api.get_journals()
        return JournivData(
            journals={journal["id"]: journal for journal in journals},
            writing=await self.api.get_writing_analytics(),
            mood_statistics=await self.api.get_mood_statistics(),
            mood_streak=await self.api.get_mood_streak(),
            user=await self.api.get_current_user(),
        )

    async def _async_authenticate(self) -> None:
        """Authenticate using a refresh token when possible."""
        if refresh_token := self.config_entry.data.get(CONF_REFRESH_TOKEN):
            await self.api.refresh_access_token(refresh_token)
            return

        await self.api.authenticate(
            email=self.config_entry.data[CONF_EMAIL],
            password=self.config_entry.data[CONF_PASSWORD],
        )
