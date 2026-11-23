"""Test the Journiv integration setup."""

from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journiv.api import JournivApi
from custom_components.journiv.const import CONF_REFRESH_TOKEN, DOMAIN
from custom_components.journiv.coordinator import JournivDataUpdateCoordinator
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

TEST_HOST = "http://journiv.example.com"
TEST_PASSWORD = "test-password"
TEST_REFRESH_TOKEN = "refresh-token"

TEST_WRITING_ANALYTICS = {
    "current_streak": 3,
    "longest_streak": 12,
    "total_entries": 42,
    "total_words": 12500,
    "average_words_per_entry": 297.6,
    "last_entry_date": "2026-11-22",
}
TEST_MOOD_STATISTICS = {
    "total_logs": 18,
    "most_frequent_mood": {"name": "Happy", "category": "positive", "count": 7},
}
TEST_MOOD_STREAK = {
    "current_streak": 2,
    "total_days_logged": 30,
    "last_logged_date": "2026-11-21",
}


async def test_setup_multiple_accounts(hass: HomeAssistant) -> None:
    """Test that each account has an isolated authenticated API client."""
    first_entry = MockConfigEntry(
        domain=DOMAIN,
        title="first@example.com",
        unique_id="12345678-1234-1234-1234-123456789abc",
        data={
            CONF_HOST: TEST_HOST,
            CONF_EMAIL: "first@example.com",
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        title="second@example.com",
        unique_id="87654321-4321-4321-4321-cba987654321",
        data={
            CONF_HOST: TEST_HOST,
            CONF_EMAIL: "second@example.com",
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    first_entry.add_to_hass(hass)
    second_entry.add_to_hass(hass)

    first_api = MagicMock(spec=JournivApi)
    first_api.access_token = None
    first_api.refresh_token = None
    first_api.authenticate = AsyncMock()
    first_api.get_journals = AsyncMock(return_value=[])
    first_api.get_writing_analytics = AsyncMock(return_value=TEST_WRITING_ANALYTICS)
    first_api.get_mood_statistics = AsyncMock(return_value=TEST_MOOD_STATISTICS)
    first_api.get_mood_streak = AsyncMock(return_value=TEST_MOOD_STREAK)
    first_api.get_current_user = AsyncMock(
        return_value={
            "id": first_entry.unique_id,
            "email": first_entry.title,
            "name": "Aled",
        }
    )
    second_api = MagicMock(spec=JournivApi)
    second_api.access_token = None
    second_api.refresh_token = None
    second_api.authenticate = AsyncMock()
    second_api.get_journals = AsyncMock(return_value=[])
    second_api.get_writing_analytics = AsyncMock(return_value=TEST_WRITING_ANALYTICS)
    second_api.get_mood_statistics = AsyncMock(return_value=TEST_MOOD_STATISTICS)
    second_api.get_mood_streak = AsyncMock(return_value=TEST_MOOD_STREAK)
    second_api.get_current_user = AsyncMock(
        return_value={
            "id": second_entry.unique_id,
            "email": second_entry.title,
            "name": "Second",
        }
    )

    with patch(
        "custom_components.journiv.JournivApi",
        side_effect=[first_api, second_api],
    ):
        assert await hass.config_entries.async_setup(first_entry.entry_id)
        await hass.async_block_till_done()

    assert first_entry.state is ConfigEntryState.LOADED
    assert second_entry.state is ConfigEntryState.LOADED
    assert isinstance(first_entry.runtime_data, JournivDataUpdateCoordinator)
    assert isinstance(second_entry.runtime_data, JournivDataUpdateCoordinator)
    assert first_entry.runtime_data.api is first_api
    assert second_entry.runtime_data.api is second_api
    first_api.authenticate.assert_awaited_once_with(
        email="first@example.com",
        password=TEST_PASSWORD,
    )
    second_api.authenticate.assert_awaited_once_with(
        email="second@example.com",
        password=TEST_PASSWORD,
    )


async def test_reload_uses_refresh_token(hass: HomeAssistant) -> None:
    """Test reload uses the refresh token without logging in again."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="first@example.com",
        unique_id="12345678-1234-1234-1234-123456789abc",
        data={
            CONF_HOST: TEST_HOST,
            CONF_EMAIL: "first@example.com",
            CONF_PASSWORD: TEST_PASSWORD,
            CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
        },
    )
    entry.add_to_hass(hass)

    api = MagicMock(spec=JournivApi)
    api.access_token = None
    api.refresh_token = TEST_REFRESH_TOKEN
    api.authenticate = AsyncMock()
    api.refresh_access_token = AsyncMock()
    api.get_journals = AsyncMock(return_value=[])
    api.get_writing_analytics = AsyncMock(return_value=TEST_WRITING_ANALYTICS)
    api.get_mood_statistics = AsyncMock(return_value=TEST_MOOD_STATISTICS)
    api.get_mood_streak = AsyncMock(return_value=TEST_MOOD_STREAK)
    api.get_current_user = AsyncMock(
        return_value={"id": entry.unique_id, "email": entry.title, "name": "Aled"}
    )

    with patch("custom_components.journiv.JournivApi", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        api.access_token = None
        api.get_journals.reset_mock()
        api.refresh_access_token.reset_mock()

        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    api.get_journals.assert_awaited_once_with()
    api.refresh_access_token.assert_awaited_once_with(TEST_REFRESH_TOKEN)
    api.authenticate.assert_not_awaited()


async def test_migrate_entry(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test legacy credentials, entities, and devices are migrated."""
    user_id = "12345678-1234-1234-1234-123456789abc"
    journal_id = "11111111-1111-1111-1111-111111111111"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="first@example.com",
        unique_id=user_id,
        version=1,
        data={
            CONF_HOST: f"{TEST_HOST}/",
            CONF_EMAIL: "first@example.com",
            CONF_PASSWORD: TEST_PASSWORD,
            CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
        },
    )
    entry.add_to_hass(hass)
    account_entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{user_id}_current_streak",
        config_entry=entry,
    )
    journal_entity = entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{journal_id}_entry_count",
        config_entry=entry,
    )
    account_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, user_id)},
    )
    journal_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, journal_id)},
    )

    assert await hass.config_entries.async_setup(entry.entry_id)

    new_account_id = f"{TEST_HOST}#{user_id}"
    assert entry.version == 2
    assert entry.unique_id == new_account_id
    assert entry.data == {
        CONF_HOST: TEST_HOST,
        CONF_EMAIL: "first@example.com",
        CONF_REFRESH_TOKEN: TEST_REFRESH_TOKEN,
    }
    assert entity_registry.async_get(account_entity.entity_id).unique_id == (
        f"{new_account_id}_current_streak"
    )
    assert entity_registry.async_get(journal_entity.entity_id).unique_id == (
        f"{new_account_id}_{journal_id}_entry_count"
    )
    assert device_registry.async_get(account_device.id).identifiers == {
        (DOMAIN, new_account_id)
    }
    assert device_registry.async_get(journal_device.id).identifiers == {
        (DOMAIN, f"{new_account_id}_{journal_id}")
    }

    assert len(mock_setup_entry.mock_calls) == 1
