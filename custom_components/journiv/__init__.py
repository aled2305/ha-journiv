"""The Journiv integration."""

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JournivApi
from .coordinator import JournivConfigEntry, JournivDataUpdateCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: JournivConfigEntry) -> None:
    """Set up Journiv from a config entry."""
    previous_coordinator = getattr(entry, "runtime_data", None)
    if isinstance(previous_coordinator, JournivDataUpdateCoordinator):
        api = previous_coordinator.api
    else:
        api = JournivApi(
            session=async_get_clientsession(hass),
            host=entry.data[CONF_HOST],
        )
    coordinator = JournivDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: JournivConfigEntry) -> None:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
