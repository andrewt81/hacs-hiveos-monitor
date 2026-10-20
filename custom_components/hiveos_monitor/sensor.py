"""Sensors for HiveOS Monitor."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .api import (
    hashrate_scale,
    worker_active_miners,
    worker_cpu_temperature,
    worker_fan_speed,
    worker_gpu_count,
    worker_gpu_memory_temperature,
    worker_gpu_temperature,
    worker_gpus,
    worker_hashrates,
    worker_id,
    worker_is_online,
    worker_load_average,
    worker_model,
    worker_name,
    worker_power,
    worker_shares,
    worker_software_version,
    worker_uptime,
)
from .const import CONF_FARM_ID, DOMAIN

Worker = dict[str, Any]
Gpu = dict[str, Any]
Coordinator = DataUpdateCoordinator[list[Worker]]


@dataclass(frozen=True, kw_only=True)
class HiveOSFarmSensorDescription(SensorEntityDescription):
    """Describe a farm-wide HiveOS sensor."""

    value_fn: Callable[[list[Worker]], int | float]


@dataclass(frozen=True, kw_only=True)
class HiveOSWorkerSensorDescription(SensorEntityDescription):
    """Describe a sensor belonging to one HiveOS worker."""

    value_fn: Callable[[Worker], int | float | str | None]


@dataclass(frozen=True, kw_only=True)
class HiveOSGpuSensorDescription(SensorEntityDescription):
    """Describe a sensor belonging to one HiveOS GPU."""

    value_fn: Callable[[Gpu], int | float | None]


FARM_SENSORS = (
    HiveOSFarmSensorDescription(key="workers", translation_key="workers", value_fn=len),
    HiveOSFarmSensorDescription(
        key="online_workers",
        translation_key="online_workers",
        value_fn=lambda data: sum(worker_is_online(worker) for worker in data),
    ),
    HiveOSFarmSensorDescription(
        key="offline_workers",
        translation_key="offline_workers",
        value_fn=lambda data: sum(not worker_is_online(worker) for worker in data),
    ),
    HiveOSFarmSensorDescription(
        key="gpus",
        translation_key="gpus",
        value_fn=lambda data: sum(worker_gpu_count(worker) for worker in data),
    ),
    HiveOSFarmSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: round(
            sum(worker_power(worker) or 0 for worker in data), 1
        ),
    ),
)

WORKER_SENSORS = (
    HiveOSWorkerSensorDescription(
        key="status",
        translation_key="worker_status",
        icon="mdi:lan-connect",
        value_fn=lambda worker: "online" if worker_is_online(worker) else "offline",
    ),
    HiveOSWorkerSensorDescription(
        key="power",
        translation_key="worker_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=worker_power,
    ),
    HiveOSWorkerSensorDescription(
        key="gpus",
        translation_key="worker_gpus",
        icon="mdi:expansion-card",
        value_fn=worker_gpu_count,
    ),
    HiveOSWorkerSensorDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=worker_cpu_temperature,
    ),
    HiveOSWorkerSensorDescription(
        key="gpu_temperature",
        translation_key="gpu_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=worker_gpu_temperature,
    ),
    HiveOSWorkerSensorDescription(
        key="gpu_memory_temperature",
        translation_key="gpu_memory_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=worker_gpu_memory_temperature,
    ),
    HiveOSWorkerSensorDescription(
        key="fan_speed",
        translation_key="fan_speed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:fan",
        value_fn=worker_fan_speed,
    ),
    HiveOSWorkerSensorDescription(
        key="load_average",
        translation_key="load_average",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:cpu-64-bit",
        value_fn=worker_load_average,
    ),
    HiveOSWorkerSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        value_fn=worker_uptime,
    ),
    HiveOSWorkerSensorDescription(
        key="active_miners",
        translation_key="active_miners",
        icon="mdi:pickaxe",
        value_fn=lambda worker: len(worker_active_miners(worker)),
    ),
    HiveOSWorkerSensorDescription(
        key="miner_names",
        translation_key="miner_names",
        icon="mdi:application-cog-outline",
        value_fn=lambda worker: ", ".join(worker_active_miners(worker)) or None,
    ),
    HiveOSWorkerSensorDescription(
        key="accepted_shares",
        translation_key="accepted_shares",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:check-circle-outline",
        value_fn=lambda worker: worker_shares(worker).get("accepted"),
    ),
    HiveOSWorkerSensorDescription(
        key="rejected_shares",
        translation_key="rejected_shares",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:close-circle-outline",
        value_fn=lambda worker: worker_shares(worker).get("rejected"),
    ),
    HiveOSWorkerSensorDescription(
        key="invalid_shares",
        translation_key="invalid_shares",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle-outline",
        value_fn=lambda worker: worker_shares(worker).get("invalid"),
    ),
)

GPU_SENSORS = (
    HiveOSGpuSensorDescription(
        key="core_temperature",
        translation_key="gpu_core_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda gpu: gpu.get("temp"),
    ),
    HiveOSGpuSensorDescription(
        key="memory_temperature",
        translation_key="gpu_individual_memory_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
        value_fn=lambda gpu: gpu.get("memtemp"),
    ),
    HiveOSGpuSensorDescription(
        key="fan_speed",
        translation_key="gpu_fan_speed",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:fan",
        value_fn=lambda gpu: gpu.get("fan"),
    ),
    HiveOSGpuSensorDescription(
        key="power",
        translation_key="gpu_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda gpu: gpu.get("power"),
    ),
    HiveOSGpuSensorDescription(
        key="core_clock",
        translation_key="gpu_core_clock",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="MHz",
        suggested_display_precision=0,
        icon="mdi:memory",
        value_fn=lambda gpu: gpu.get("coreclk"),
    ),
    HiveOSGpuSensorDescription(
        key="memory_clock",
        translation_key="gpu_memory_clock",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="MHz",
        suggested_display_precision=0,
        icon="mdi:memory",
        value_fn=lambda gpu: gpu.get("memclk"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up farm and per-worker HiveOS sensors."""
    coordinator: Coordinator = entry.runtime_data
    async_add_entities(
        HiveOSFarmSensor(coordinator, entry, description)
        for description in FARM_SENSORS
    )

    added: set[tuple[str, str]] = set()
    entity_registry = er.async_get(hass)
    initial_discovery = True

    def async_add_worker_entities() -> None:
        nonlocal initial_discovery
        entities: list[SensorEntity] = []
        for worker in coordinator.data:
            identifier = worker_id(worker)
            if identifier is None:
                continue
            for description in WORKER_SENSORS:
                key = (identifier, description.key)
                if key not in added:
                    added.add(key)
                    entities.append(
                        HiveOSWorkerSensor(
                            coordinator, entry, identifier, description
                        )
                    )
            for algorithm in worker_hashrates(worker):
                key = (identifier, f"hashrate_{algorithm}")
                if key not in added:
                    added.add(key)
                    entities.append(
                        HiveOSWorkerHashrateSensor(
                            coordinator, entry, identifier, algorithm
                        )
                    )
            for gpu in worker_gpus(worker):
                gpu_identifier = str(gpu["id"])
                legacy_load_unique_id = (
                    f"{entry.data[CONF_FARM_ID]}_{identifier}_gpu_"
                    f"{gpu_identifier}_load"
                )
                legacy_load_entity_id = entity_registry.async_get_entity_id(
                    "sensor", DOMAIN, legacy_load_unique_id
                )
                if initial_discovery and legacy_load_entity_id:
                    entity_registry.async_remove(legacy_load_entity_id)
                for description in GPU_SENSORS:
                    unique_id = (
                        f"{entry.data[CONF_FARM_ID]}_{identifier}_gpu_"
                        f"{gpu_identifier}_{description.key}"
                    )
                    if description.value_fn(gpu) is None:
                        stale_entity_id = entity_registry.async_get_entity_id(
                            "sensor", DOMAIN, unique_id
                        )
                        if initial_discovery and stale_entity_id:
                            entity_registry.async_remove(stale_entity_id)
                        continue
                    key = (identifier, f"gpu_{gpu_identifier}_{description.key}")
                    if key not in added:
                        added.add(key)
                        entities.append(
                            HiveOSGpuSensor(
                                coordinator,
                                entry,
                                identifier,
                                gpu_identifier,
                                description,
                            )
                        )
                for algorithm in gpu.get("hashrates", {}):
                    key = (
                        identifier,
                        f"gpu_{gpu_identifier}_hashrate_{algorithm}",
                    )
                    if key not in added:
                        added.add(key)
                        entities.append(
                            HiveOSGpuHashrateSensor(
                                coordinator,
                                entry,
                                identifier,
                                gpu_identifier,
                                algorithm,
                            )
                        )
        if entities:
            async_add_entities(entities)
        initial_discovery = False

    async_add_worker_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_add_worker_entities))


class HiveOSFarmSensor(CoordinatorEntity[Coordinator], SensorEntity):
    """A farm-wide sensor backed by the shared HiveOS coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Coordinator,
        entry: ConfigEntry,
        description: HiveOSFarmSensorDescription,
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
        """Return the current farm sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)


class HiveOSWorkerEntity(CoordinatorEntity[Coordinator]):
    """Base class for entities belonging to a HiveOS worker."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: Coordinator, entry: ConfigEntry, identifier: str
    ) -> None:
        super().__init__(coordinator)
        self._identifier = identifier
        self._farm_id = str(entry.data[CONF_FARM_ID])
        worker = self._worker
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{self._farm_id}_{identifier}")},
            "name": worker_name(worker) if worker else f"HiveOS worker {identifier}",
            "manufacturer": "HiveOS",
            "model": worker_model(worker) if worker else "Mining worker",
            "sw_version": worker_software_version(worker) if worker else None,
            "via_device": (DOMAIN, self._farm_id),
        }

    @property
    def _worker(self) -> Worker | None:
        return next(
            (
                worker
                for worker in self.coordinator.data
                if worker_id(worker) == self._identifier
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Return whether the worker is still present in the API response."""
        return super().available and self._worker is not None


class HiveOSWorkerSensor(HiveOSWorkerEntity, SensorEntity):
    """A sensor exposing one metric for a single worker."""

    def __init__(
        self,
        coordinator: Coordinator,
        entry: ConfigEntry,
        identifier: str,
        description: HiveOSWorkerSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, identifier)
        self.entity_description = description
        self._attr_unique_id = f"{self._farm_id}_{identifier}_{description.key}"

    @property
    def native_value(self) -> int | float | str | None:
        """Return the current worker sensor value."""
        worker = self._worker
        return self.entity_description.value_fn(worker) if worker else None


class HiveOSWorkerHashrateSensor(HiveOSWorkerEntity, SensorEntity):
    """A dynamically discovered worker hashrate sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:speedometer"

    def __init__(
        self,
        coordinator: Coordinator,
        entry: ConfigEntry,
        identifier: str,
        algorithm: str,
    ) -> None:
        super().__init__(coordinator, entry, identifier)
        self._algorithm = algorithm
        algorithm_key = re.sub(r"[^a-z0-9]+", "_", algorithm.lower()).strip("_")
        self._attr_unique_id = (
            f"{self._farm_id}_{identifier}_hashrate_{algorithm_key}"
        )
        self._attr_name = f"Hashrate {algorithm}"
        worker = self._worker
        current_value = (
            worker_hashrates(worker).get(algorithm) if worker else None
        )
        self._hashrate_divisor, self._attr_native_unit_of_measurement = (
            hashrate_scale(current_value)
        )

    @property
    def native_value(self) -> float | None:
        """Return the current hashrate for this algorithm."""
        worker = self._worker
        value = worker_hashrates(worker).get(self._algorithm) if worker else None
        return value / self._hashrate_divisor if value is not None else None


class HiveOSGpuEntity(HiveOSWorkerEntity):
    """Base class for entities belonging to one GPU."""

    def __init__(
        self,
        coordinator: Coordinator,
        entry: ConfigEntry,
        identifier: str,
        gpu_identifier: str,
    ) -> None:
        super().__init__(coordinator, entry, identifier)
        self._gpu_identifier = gpu_identifier
        gpu = self._gpu
        gpu_index = gpu.get("index") if gpu else gpu_identifier
        brand = str(gpu.get("brand") or "HiveOS") if gpu else "HiveOS"
        model = (
            str(gpu.get("short_name") or gpu.get("model") or "GPU")
            if gpu
            else "GPU"
        )
        worker = self._worker
        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, f"{self._farm_id}_{identifier}_gpu_{gpu_identifier}")
            },
            "name": (
                f"{worker_name(worker)} GPU {gpu_index}"
                if worker
                else f"GPU {gpu_index}"
            ),
            "manufacturer": brand.upper(),
            "model": model,
            "via_device": (DOMAIN, f"{self._farm_id}_{identifier}"),
        }

    @property
    def _gpu(self) -> Gpu | None:
        worker = self._worker
        if worker is None:
            return None
        return next(
            (
                gpu
                for gpu in worker_gpus(worker)
                if str(gpu["id"]) == self._gpu_identifier
            ),
            None,
        )

    @property
    def available(self) -> bool:
        """Return whether this GPU is still reported by HiveOS."""
        return super().available and self._gpu is not None


class HiveOSGpuSensor(HiveOSGpuEntity, SensorEntity):
    """A sensor exposing one metric for a single GPU."""

    def __init__(
        self,
        coordinator: Coordinator,
        entry: ConfigEntry,
        identifier: str,
        gpu_identifier: str,
        description: HiveOSGpuSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, identifier, gpu_identifier)
        self.entity_description = description
        self._attr_unique_id = (
            f"{self._farm_id}_{identifier}_gpu_{gpu_identifier}_{description.key}"
        )

    @property
    def native_value(self) -> int | float | None:
        """Return the current GPU sensor value."""
        gpu = self._gpu
        return self.entity_description.value_fn(gpu) if gpu else None


class HiveOSGpuHashrateSensor(HiveOSGpuEntity, SensorEntity):
    """A dynamically discovered per-GPU hashrate sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:speedometer"

    def __init__(
        self,
        coordinator: Coordinator,
        entry: ConfigEntry,
        identifier: str,
        gpu_identifier: str,
        algorithm: str,
    ) -> None:
        super().__init__(coordinator, entry, identifier, gpu_identifier)
        self._algorithm = algorithm
        algorithm_key = re.sub(r"[^a-z0-9]+", "_", algorithm.lower()).strip("_")
        self._attr_unique_id = (
            f"{self._farm_id}_{identifier}_gpu_{gpu_identifier}_"
            f"hashrate_{algorithm_key}"
        )
        self._attr_name = f"Hashrate {algorithm}"
        gpu = self._gpu
        current_value = (
            gpu.get("hashrates", {}).get(algorithm) if gpu else None
        )
        self._hashrate_divisor, self._attr_native_unit_of_measurement = (
            hashrate_scale(current_value)
        )

    @property
    def native_value(self) -> float | None:
        """Return this GPU's current hashrate for the algorithm."""
        gpu = self._gpu
        if gpu is None:
            return None
        value = gpu.get("hashrates", {}).get(self._algorithm)
        return value / self._hashrate_divisor if value is not None else None
