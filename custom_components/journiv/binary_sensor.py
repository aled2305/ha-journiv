"""Binary sensor platform for Journiv."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import JournivJournal
from .const import CONF_JOURNAL_IDS
from .coordinator import JournivConfigEntry, JournivDataUpdateCoordinator
from .entity import JournivEntity


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
    known_journal_ids: set[str] = set()

    @callback
    def _async_add_new_journals() -> None:
        """Add entities for selected journals that have become available."""
        new_journal_ids = (
            set(selected_journal_ids) & coordinator.data.journals.keys()
        ) - known_journal_ids
        if not new_journal_ids:
            return
        async_add_entities(
            JournivBinarySensor(coordinator, entry, journal_id, description)
            for journal_id in sorted(new_journal_ids)
            for description in BINARY_SENSORS
        )
        known_journal_ids.update(new_journal_ids)

    _async_add_new_journals()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_journals))


class JournivBinarySensor(JournivEntity, BinarySensorEntity):
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
        super().__init__(coordinator, entry, journal_id)
        self.entity_description = description
        account_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{account_id}_{journal_id}_{description.key}"

    @property
    @override
    def is_on(self) -> bool | None:
        """Return the journal flag state."""
        journal = self.coordinator.data.journals.get(self._journal_id)
        if journal is None:
            return None
        return self.entity_description.value_fn(journal)
