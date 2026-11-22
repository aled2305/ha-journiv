"""Tests for Journiv sensors."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_EMAIL, CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.journiv.api import JournivApi
from custom_components.journiv.const import CONF_JOURNAL_IDS, DOMAIN

TEST_HOST = "http://journiv.example.com"
TEST_JOURNAL_ID = "11111111-1111-1111-1111-111111111111"
TEST_SECOND_JOURNAL_ID = "22222222-2222-2222-2222-222222222222"

TEST_JOURNALS = [
    {
        "id": TEST_JOURNAL_ID,
        "title": "Personal",
        "entry_count": 42,
        "total_words": 12500,
        "last_entry_at": "2026-11-22T15:30:00Z",
        "is_favorite": True,
        "is_archived": False,
    },
    {
        "id": TEST_SECOND_JOURNAL_ID,
        "title": "Travel",
        "entry_count": 8,
        "total_words": 3200,
        "last_entry_at": None,
        "is_favorite": False,
        "is_archived": True,
    },
]

TEST_WRITING_ANALYTICS = {
    "current_streak": 3,
    "longest_streak": 12,
    "total_entries": 50,
    "total_words": 15700,
    "average_words_per_entry": 314.0,
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


async def test_selected_journal_sensors(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Test sensors are created for selected journals only."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="test@example.com",
        unique_id="12345678-1234-1234-1234-123456789abc",
        data={
            CONF_HOST: TEST_HOST,
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "test-password",
        },
        options={CONF_JOURNAL_IDS: [TEST_JOURNAL_ID]},
    )
    entry.add_to_hass(hass)

    api = MagicMock(spec=JournivApi)
    api.access_token = None
    api.refresh_token = None
    api.authenticate = AsyncMock()
    api.get_journals = AsyncMock(return_value=TEST_JOURNALS)
    api.get_writing_analytics = AsyncMock(return_value=TEST_WRITING_ANALYTICS)
    api.get_mood_statistics = AsyncMock(return_value=TEST_MOOD_STATISTICS)
    api.get_mood_streak = AsyncMock(return_value=TEST_MOOD_STREAK)
    api.get_current_user = AsyncMock(
        return_value={"id": entry.unique_id, "email": entry.title, "name": "Aled"}
    )

    with patch("custom_components.journiv.JournivApi", return_value=api):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entries = hass.states.get("sensor.personal_entries")
    assert entries is not None
    assert entries.state == "42"

    total_words = hass.states.get("sensor.personal_total_words")
    assert total_words is not None
    assert total_words.state == "12500"
    assert total_words.attributes["unit_of_measurement"] == "words"

    last_entry = hass.states.get("sensor.personal_last_entry")
    assert last_entry is not None
    assert last_entry.state == "2026-11-22T15:30:00+00:00"
    assert last_entry.attributes["device_class"] == "timestamp"

    assert hass.states.get("sensor.travel_entries") is None

    favorite = hass.states.get("binary_sensor.personal_favorite")
    assert favorite is not None
    assert favorite.state == "on"

    archived = hass.states.get("binary_sensor.personal_archived")
    assert archived is not None
    assert archived.state == "off"

    current_streak = hass.states.get("sensor.aled_s_overview_current_writing_streak")
    assert current_streak is not None
    assert current_streak.state == "3"

    most_frequent_mood = hass.states.get(
        "sensor.aled_s_overview_most_frequent_mood_30_days"
    )
    assert most_frequent_mood is not None
    assert most_frequent_mood.state == "Happy"

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, TEST_JOURNAL_ID), entry.entry_id
    )
    assert device is not None
    assert device.name == "Personal"
    assert device.manufacturer == "Journiv"
    assert device.model == "Journal"

    account_device = device_registry.async_get_device_by_identifier(
        (DOMAIN, entry.unique_id), entry.entry_id
    )
    assert account_device is not None
    assert account_device.name == "Aled's overview"
    assert account_device.model == "Account"
