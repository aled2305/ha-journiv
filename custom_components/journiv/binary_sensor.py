"""Binary sensor platform for Journiv."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import JournivJournal
from .const import CONF_JOURNAL_IDS, DOMAIN
from .coordinator import JournivConfigEntry, JournivDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class JournivBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a Journiv binary sensor."""

    value_fn: Callable[[JournivJournal], bool]


BINARY_SENSORS: tuple[JournivBinarySensorEntityDescription, ...] = (
    JournivBinarySensorEntityDescription(
        key="favorite",
        translation_key="favorite",
        value_fn=lambda journal: journal["is_favorite"],
    ),
    JournivBinarySensorEntityDescription(
        key="archived",
        translation_key="archived",
        value_fn=lambda journal: journal["is_archived"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JournivConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Journiv binary sensors."""
    coordinator = entry.runtime_data
    selected_journal_ids = entry.options.get(CONF_JOURNAL_IDS, [])
    async_add_entities(
        JournivBinarySensor(coordinator, entry, journal_id, description)
        for journal_id in selected_journal_ids
        if journal_id in coordinator.data.journals
        for description in BINARY_SENSORS
    )


class JournivBinarySensor(
    CoordinatorEntity[JournivDataUpdateCoordinator], BinarySensorEntity
):
    """Represent a Journiv journal flag."""

    _attr_has_entity_name = True
    entity_description: JournivBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: JournivDataUpdateCoordinator,
        entry: JournivConfigEntry,
        journal_id: str,
        description: JournivBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        journal = coordinator.data.journals[journal_id]
        self.entity_description = description
        self._journal_id = journal_id
        self._attr_unique_id = f"{journal_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, journal_id)},
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

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the journal flag state."""
        journal = self.coordinator.data.journals.get(self._journal_id)
        if journal is None:
            return None
        return self.entity_description.value_fn(journal)
