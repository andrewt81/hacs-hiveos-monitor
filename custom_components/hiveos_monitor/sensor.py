"""Sensors for HiveOS Monitor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import worker_gpu_count, worker_is_online, worker_power
from .const import CONF_FARM_ID, DOMAIN


@dataclass(frozen=True, kw_only=True)
class HiveOSSensorDescription(SensorEntityDescription):
    """Describe a HiveOS sensor."""

    value_fn: Callable[[list[dict[str, Any]]], int | float]


SENSORS = (
    HiveOSSensorDescription(key="workers", translation_key="workers", value_fn=len),
    HiveOSSensorDescription(
        key="online_workers",
        translation_key="online_workers",
        value_fn=lambda data: sum(worker_is_online(worker) for worker in data),
    ),
    HiveOSSensorDescription(
        key="offline_workers",
        translation_key="offline_workers",
        value_fn=lambda data: sum(not worker_is_online(worker) for worker in data),
    ),
    HiveOSSensorDescription(
        key="gpus",
        translation_key="gpus",
        value_fn=lambda data: sum(worker_gpu_count(worker) for worker in data),
    ),
    HiveOSSensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: round(sum(worker_power(worker) for worker in data), 1),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up HiveOS sensors."""
    coordinator = entry.runtime_data
    async_add_entities(HiveOSSensor(coordinator, entry, item) for item in SENSORS)


class HiveOSSensor(CoordinatorEntity[DataUpdateCoordinator], SensorEntity):
    """A sensor backed by the shared HiveOS coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry: ConfigEntry,
        description: HiveOSSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        farm_id = entry.data[CONF_FARM_ID]
        self._attr_unique_id = f"{farm_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, farm_id)},
            "name": f"HiveOS farm {farm_id}",
            "manufacturer": "HiveOS",
            "model": "Cloud farm",
        }

    @property
    def native_value(self) -> int | float:
        """Return the current sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
