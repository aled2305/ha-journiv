"""Sensor platform for Journiv."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_HOST, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import JournivJournal
from .const import CONF_JOURNAL_IDS, DOMAIN
from .coordinator import JournivConfigEntry, JournivData, JournivDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class JournivSensorEntityDescription(SensorEntityDescription):
    """Describe a Journiv sensor."""

    value_fn: Callable[[JournivJournal], StateType | datetime]


SENSORS: tuple[JournivSensorEntityDescription, ...] = (
    JournivSensorEntityDescription(
        key="entry_count",
        translation_key="entry_count",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda journal: journal["entry_count"],
    ),
    JournivSensorEntityDescription(
        key="total_words",
        translation_key="total_words",
        native_unit_of_measurement="words",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda journal: journal["total_words"],
    ),
    JournivSensorEntityDescription(
        key="last_entry",
        translation_key="last_entry",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda journal: (
            dt_util.parse_datetime(journal["last_entry_at"])
            if journal["last_entry_at"]
            else None
        ),
    ),
)


@dataclass(frozen=True, kw_only=True)
class JournivAccountSensorEntityDescription(SensorEntityDescription):
    """Describe a Journiv account sensor."""

    value_fn: Callable[[JournivData], StateType | date]


ACCOUNT_SENSORS: tuple[JournivAccountSensorEntityDescription, ...] = (
    JournivAccountSensorEntityDescription(
        key="current_streak",
        translation_key="current_streak",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.writing["current_streak"],
    ),
    JournivAccountSensorEntityDescription(
        key="longest_streak",
        translation_key="longest_streak",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.writing["longest_streak"],
    ),
    JournivAccountSensorEntityDescription(
        key="total_entries",
        translation_key="total_entries",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.writing["total_entries"],
    ),
    JournivAccountSensorEntityDescription(
        key="total_words",
        translation_key="total_words",
        native_unit_of_measurement="words",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.writing["total_words"],
    ),
    JournivAccountSensorEntityDescription(
        key="average_words_per_entry",
        translation_key="average_words_per_entry",
        native_unit_of_measurement="words",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.writing["average_words_per_entry"],
    ),
    JournivAccountSensorEntityDescription(
        key="last_entry_date",
        translation_key="last_entry_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: (
            dt_util.parse_date(data.writing["last_entry_date"])
            if "last_entry_date" in data.writing
            else None
        ),
    ),
    JournivAccountSensorEntityDescription(
        key="mood_current_streak",
        translation_key="mood_current_streak",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.mood_streak["current_streak"],
    ),
    JournivAccountSensorEntityDescription(
        key="mood_days_logged",
        translation_key="mood_days_logged",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.mood_streak["total_days_logged"],
    ),
    JournivAccountSensorEntityDescription(
        key="last_mood_log_date",
        translation_key="last_mood_log_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: (
            dt_util.parse_date(data.mood_streak["last_logged_date"])
            if "last_logged_date" in data.mood_streak
            else None
        ),
    ),
    JournivAccountSensorEntityDescription(
        key="mood_logs_30_days",
        translation_key="mood_logs_30_days",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.mood_statistics["total_logs"],
    ),
    JournivAccountSensorEntityDescription(
        key="most_frequent_mood_30_days",
        translation_key="most_frequent_mood_30_days",
        value_fn=lambda data: (
            data.mood_statistics["most_frequent_mood"]["name"]
            if "most_frequent_mood" in data.mood_statistics
            else None
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: JournivConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Journiv sensors."""
    coordinator = entry.runtime_data
    selected_journal_ids = entry.options.get(CONF_JOURNAL_IDS, [])
    async_add_entities(
        [
            JournivAccountSensor(coordinator, entry, description)
            for description in ACCOUNT_SENSORS
        ]
        + [
            JournivSensor(coordinator, entry, journal_id, description)
            for journal_id in selected_journal_ids
            if journal_id in coordinator.data.journals
            for description in SENSORS
        ]
    )


class JournivSensor(CoordinatorEntity[JournivDataUpdateCoordinator], SensorEntity):
    """Represent a Journiv journal statistic."""

    _attr_has_entity_name = True
    entity_description: JournivSensorEntityDescription

    def __init__(
        self,
        coordinator: JournivDataUpdateCoordinator,
        entry: JournivConfigEntry,
        journal_id: str,
        description: JournivSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
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
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        journal = self.coordinator.data.journals.get(self._journal_id)
        if journal is None:
            return None
        return self.entity_description.value_fn(journal)


class JournivAccountSensor(
    CoordinatorEntity[JournivDataUpdateCoordinator], SensorEntity
):
    """Represent a Journiv account statistic."""

    _attr_has_entity_name = True
    entity_description: JournivAccountSensorEntityDescription

    def __init__(
        self,
        coordinator: JournivDataUpdateCoordinator,
        entry: JournivConfigEntry,
        description: JournivAccountSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        account_id = entry.unique_id or entry.entry_id
        account_name = coordinator.data.user.get("name")
        device_name = (
            f"{account_name.strip()}'s overview"
            if account_name and account_name.strip()
            else "Journiv overview"
        )
        self._attr_unique_id = f"{account_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            name=device_name,
            manufacturer="Journiv",
            model="Account",
            configuration_url=entry.data[CONF_HOST],
        )

    @property
    @override
    def native_value(self) -> StateType | date:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
