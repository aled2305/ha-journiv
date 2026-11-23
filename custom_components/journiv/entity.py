"""Base entity for the Journiv integration."""

from typing import override

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JournivConfigEntry, JournivDataUpdateCoordinator


class JournivEntity(CoordinatorEntity[JournivDataUpdateCoordinator]):
    """Base class for Journiv journal entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JournivDataUpdateCoordinator,
        entry: JournivConfigEntry,
        journal_id: str,
    ) -> None:
        """Initialize a Journiv journal entity."""
        super().__init__(coordinator)
        journal = coordinator.data.journals[journal_id]
        account_id = entry.unique_id or entry.entry_id
        self._journal_id = journal_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_id}_{journal_id}")},
            name=journal["title"],
            manufacturer="Journiv",
            model="Journal",
            configuration_url=entry.data[CONF_HOST],
        )

    @property
    @override
    def available(self) -> bool:
        """Return whether the journal is available."""
        return super().available and self._journal_id in self.coordinator.data.journals
