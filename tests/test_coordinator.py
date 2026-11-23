"""Tests for the Journiv data update coordinator."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journiv.api import (
    JournivApi,
    JournivAuthenticationError,
    JournivConnectionError,
)
from custom_components.journiv.const import CONF_REFRESH_TOKEN, DOMAIN
from custom_components.journiv.coordinator import JournivDataUpdateCoordinator
from homeassistant.const import CONF_EMAIL, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

HOST = "https://journiv.example.com"
REFRESH_TOKEN = "refresh-token"


def _api() -> MagicMock:
    """Return a mocked Journiv API with valid data."""
    api = MagicMock(spec=JournivApi)
    api.access_token = "access-token"
    api.refresh_token = REFRESH_TOKEN
    api.refresh_access_token = AsyncMock()
    api.get_journals = AsyncMock(return_value=[])
    api.get_writing_analytics = AsyncMock(
        return_value={
            "current_streak": 1,
            "longest_streak": 2,
            "total_entries": 3,
            "total_words": 4,
            "average_words_per_entry": 1.3,
        }
    )
    api.get_mood_statistics = AsyncMock(return_value={"total_logs": 0})
    api.get_mood_streak = AsyncMock(
        return_value={"current_streak": 0, "total_days_logged": 0}
    )
    api.get_current_user = AsyncMock(
        return_value={"id": "user-id", "email": "test@example.com"}
    )
    return api


def _entry(hass: HomeAssistant, refresh_token: str = REFRESH_TOKEN) -> MockConfigEntry:
    """Create a config entry for coordinator tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test@example.com",
        unique_id=f"{HOST}#user-id",
        version=2,
        data={
            CONF_HOST: HOST,
            CONF_EMAIL: "test@example.com",
            CONF_REFRESH_TOKEN: refresh_token,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_authentication_failure(hass: HomeAssistant) -> None:
    """Test expired credentials request reauthentication."""
    entry = _entry(hass)
    api = _api()
    api.access_token = None
    api.refresh_access_token = AsyncMock(
        side_effect=JournivAuthenticationError("Expired token")
    )
    coordinator = JournivDataUpdateCoordinator(hass, entry, api)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_connection_failure(hass: HomeAssistant) -> None:
    """Test connection failures become update failures."""
    entry = _entry(hass)
    api = _api()
    api.get_journals = AsyncMock(
        side_effect=JournivConnectionError("Connection failed")
    )
    coordinator = JournivDataUpdateCoordinator(hass, entry, api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_retry_after_access_token_expires(hass: HomeAssistant) -> None:
    """Test an expired access token is refreshed and retried once."""
    entry = _entry(hass)
    api = _api()
    api.get_journals = AsyncMock(
        side_effect=[JournivAuthenticationError("Expired token"), []]
    )
    coordinator = JournivDataUpdateCoordinator(hass, entry, api)

    data = await coordinator._async_update_data()

    assert data.journals == {}
    api.refresh_access_token.assert_awaited_once_with(REFRESH_TOKEN)
    assert api.get_journals.await_count == 2


async def test_new_refresh_token_is_persisted(hass: HomeAssistant) -> None:
    """Test a changed refresh token is saved without restoring the password."""
    entry = _entry(hass, "old-token")
    api = _api()
    coordinator = JournivDataUpdateCoordinator(hass, entry, api)

    await coordinator._async_update_data()

    assert entry.data == {
        CONF_HOST: HOST,
        CONF_EMAIL: "test@example.com",
        CONF_REFRESH_TOKEN: REFRESH_TOKEN,
    }
