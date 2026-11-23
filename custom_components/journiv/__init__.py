"""The Journiv integration."""

from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import JournivApi, normalize_host
from .const import CONF_REFRESH_TOKEN
from .coordinator import JournivConfigEntry, JournivDataUpdateCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: JournivConfigEntry) -> bool:
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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: JournivConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: JournivConfigEntry) -> bool:
    """Migrate old config entries."""
    host = normalize_host(entry.data[CONF_HOST]) or entry.data[CONF_HOST].rstrip("/")
    old_account_id = entry.unique_id or entry.entry_id
    new_account_id = f"{host}#{old_account_id}"

    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity.unique_id.startswith(f"{old_account_id}_"):
            new_unique_id = entity.unique_id.replace(old_account_id, new_account_id, 1)
        else:
            new_unique_id = f"{new_account_id}_{entity.unique_id}"
        entity_registry.async_update_entity(
            entity.entity_id, new_unique_id=new_unique_id
        )

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        new_identifiers = {
            (
                domain,
                (
                    new_account_id
                    if identifier == old_account_id
                    else f"{new_account_id}_{identifier}"
                ),
            )
            for domain, identifier in device.identifiers
        }
        device_registry.async_update_device(device.id, new_identifiers=new_identifiers)

    data = {**entry.data, CONF_HOST: host}
    if CONF_REFRESH_TOKEN in data:
        data.pop(CONF_PASSWORD, None)
    hass.config_entries.async_update_entry(
        entry,
        data=data,
        unique_id=new_account_id,
        version=2,
    )
    return True
