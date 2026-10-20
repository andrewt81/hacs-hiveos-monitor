"""Small asynchronous client for the read-only HiveOS API calls we use."""

from __future__ import annotations

import math
import time
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import API_BASE_URL


class HiveOSAPIError(Exception):
    """Base error raised by the HiveOS client."""


class HiveOSAuthError(HiveOSAPIError):
    """Authentication failed."""


def extract_workers(payload: Any) -> list[dict[str, Any]]:
    """Extract workers from the response shapes used by HiveOS API revisions."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "workers", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = extract_workers(value)
            if nested:
                return nested
    return []


def _nested_value(data: dict[str, Any], *path: str) -> Any:
    """Return a value from a nested dictionary."""
    value: Any = data
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _number(value: Any) -> float | None:
    """Return a finite-looking numeric value without accepting booleans."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value)
            return number if math.isfinite(number) else None
        except ValueError:
            return None
    return None


def _first_number(worker: dict[str, Any], *paths: tuple[str, ...]) -> float | None:
    """Return the first numeric value found in a list of paths."""
    for path in paths:
        value = _number(_nested_value(worker, *path))
        if value is not None:
            return value
    return None


def _object_list(value: Any) -> list[dict[str, Any]]:
    """Normalize a list or index-keyed dictionary of objects."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return []


def worker_id(worker: dict[str, Any]) -> str | None:
    """Return the stable HiveOS worker identifier."""
    for key in ("id", "worker_id"):
        value = worker.get(key)
        if isinstance(value, (str, int)) and str(value):
            return str(value)
    return None


def worker_name(worker: dict[str, Any]) -> str:
    """Return a human-friendly worker name."""
    for key in ("name", "hostname"):
        value = worker.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    identifier = worker_id(worker)
    return f"Worker {identifier}" if identifier else "HiveOS worker"


def worker_is_online(worker: dict[str, Any]) -> bool:
    """Return an online state while tolerating API field variations."""
    for path in (
        ("online",),
        ("is_online",),
        ("stats", "online"),
        ("stats", "is_online"),
    ):
        value = _nested_value(worker, *path)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
    for path in (("status",), ("stats", "status")):
        status = str(_nested_value(worker, *path) or "").lower()
        if status:
            return status in {"ok", "online", "working"}
    return False


def worker_gpu_count(worker: dict[str, Any]) -> int:
    """Return the number of GPUs reported for a worker."""
    value = _first_number(
        worker,
        ("gpu_count",),
        ("gpus_count",),
        ("gpu_summary", "gpus"),
        ("gpu_summary", "gpus_count"),
        ("gpu_summary", "total"),
        ("gpu_summary", "count"),
    )
    if value is not None:
        return int(value)
    for key in ("gpus", "gpu_stats", "gpu_info"):
        items = _object_list(worker.get(key))
        if items:
            return len(items)
    return 0


def _bus_key(value: Any) -> str | None:
    """Return a comparable PCI bus key."""
    if isinstance(value, (str, int)) and str(value).strip():
        return str(value).strip().lower()
    return None


def _gpu_hashrates(
    worker: dict[str, Any], gpu_bus_keys: list[str | None]
) -> list[dict[str, float]]:
    """Return per-GPU hashrates, matching HiveOS bus arrays when available."""
    totals: list[dict[str, float]] = [{} for _ in gpu_bus_keys]

    def add_values(item: dict[str, Any], name_key: str, coin_key: str,
                   values_key: str, buses_key: str) -> None:
        name = item.get(name_key) or item.get(coin_key)
        values = item.get(values_key)
        if not name or not isinstance(values, (list, tuple)):
            return
        label = str(name).lower()
        buses = item.get(buses_key)
        bus_indexes = {
            key: index
            for index, value in enumerate(buses)
            if (key := _bus_key(value)) is not None
        } if isinstance(buses, (list, tuple)) else {}
        for position, raw_value in enumerate(values):
            value = _number(raw_value)
            if value is None:
                continue
            target = position
            if bus_indexes:
                target = next(
                    (
                        index
                        for index, bus_key in enumerate(gpu_bus_keys)
                        if bus_key is not None
                        and bus_indexes.get(bus_key) == position
                    ),
                    -1,
                )
            if 0 <= target < len(totals):
                totals[target][label] = totals[target].get(label, 0.0) + value

    detailed = _object_list(_nested_value(worker, "miners_stats", "hashrates"))
    summary = _object_list(_nested_value(worker, "miners_summary", "hashrates"))
    entries = detailed if any(
        item.get("hashes") or item.get("dhashes") for item in detailed
    ) else summary
    for item in entries:
        add_values(item, "algo", "coin", "hashes", "bus_numbers")
        add_values(item, "dalgo", "dcoin", "dhashes", "dbus_numbers")
    return totals


def _gpu_stat_value(
    info: dict[str, Any], stats: dict[str, Any], *keys: str
) -> float | None:
    """Return a GPU statistic across API revisions and response shapes."""
    nested_stats = info.get("stats")
    sources = (stats, nested_stats if isinstance(nested_stats, dict) else {}, info)
    for source in sources:
        for key in keys:
            value = _number(source.get(key))
            if value is not None:
                return value
    return None


def worker_gpus(worker: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized per-GPU information and statistics for a worker."""
    info_items = _object_list(worker.get("gpu_info"))
    stats_items = _object_list(worker.get("gpu_stats"))
    stats_by_bus = {
        key: item
        for item in stats_items
        if (key := _bus_key(item.get("bus_number"))) is not None
    }
    count = max(len(info_items), len(stats_items))
    gpus: list[dict[str, Any]] = []
    bus_keys: list[str | None] = []

    for position in range(count):
        info = info_items[position] if position < len(info_items) else {}
        bus_key = _bus_key(info.get("bus_number"))
        stats = stats_by_bus.get(bus_key) if bus_key is not None else None
        if stats is None and position < len(stats_items):
            stats = stats_items[position]
        stats = stats or {}
        if bus_key is None:
            bus_key = _bus_key(stats.get("bus_number"))

        display_index = info.get("index", position)
        stable_id = (
            _bus_key(info.get("bus_id"))
            or bus_key
            or _bus_key(display_index)
            or str(position)
        )
        gpu = {
            "id": stable_id,
            "index": display_index,
            "bus_id": info.get("bus_id"),
            "bus_number": info.get("bus_number", stats.get("bus_number")),
            "brand": info.get("brand"),
            "model": info.get("model"),
            "short_name": info.get("short_name"),
        }
        gpu.update(
            {
                "temp": _gpu_stat_value(
                    info, stats, "temp", "temperature", "core_temp"
                ),
                "memtemp": _gpu_stat_value(
                    info,
                    stats,
                    "memtemp",
                    "mem_temp",
                    "memory_temp",
                    "mtemp",
                    "junction_temp",
                ),
                "fan": _gpu_stat_value(
                    info, stats, "fan", "fan_speed", "fanspeed"
                ),
                "power": _gpu_stat_value(
                    info, stats, "power", "power_draw", "watt"
                ),
                "coreclk": _gpu_stat_value(
                    info,
                    stats,
                    "coreclk",
                    "core_clock",
                    "coreClock",
                    "clock_core",
                ),
                "memclk": _gpu_stat_value(
                    info,
                    stats,
                    "memclk",
                    "mem_clock",
                    "memory_clock",
                    "memoryClock",
                    "clock_memory",
                ),
                "load": _gpu_stat_value(
                    info,
                    stats,
                    "load",
                    "gpu_load",
                    "utilization",
                    "usage",
                    "core_load",
                ),
            }
        )
        gpus.append(gpu)
        bus_keys.append(bus_key)

    for gpu, hashrates in zip(gpus, _gpu_hashrates(worker, bus_keys), strict=True):
        gpu["hashrates"] = hashrates
    return gpus


def worker_power(worker: dict[str, Any]) -> float | None:
    """Return worker power in watts, if present."""
    return _first_number(
        worker,
        ("power_draw",),
        ("power",),
        ("watt",),
        ("gpu_summary", "power_draw"),
        ("gpu_summary", "power"),
        ("stats", "power_draw"),
        ("stats", "power"),
        ("hardware_stats", "power_draw"),
        ("hardware_stats", "power"),
        ("asic_stats", "power_draw"),
        ("asic_stats", "power"),
    )


def worker_cpu_temperature(worker: dict[str, Any]) -> float | None:
    """Return CPU temperature in degrees Celsius."""
    value = _first_number(
        worker,
        ("cpu_temp",),
        ("stats", "cpu_temp"),
        ("hardware_stats", "cpu_temp"),
    )
    if value is not None:
        return value
    temperatures = _nested_value(worker, "hardware_stats", "cputemp")
    if isinstance(temperatures, (list, tuple)):
        values = [
            value
            for item in temperatures
            if (value := _number(item)) is not None
        ]
        return max(values) if values else None
    return _number(temperatures)


def _gpu_values(worker: dict[str, Any], *keys: str) -> list[float]:
    values: list[float] = []
    for gpu in _object_list(worker.get("gpu_stats")):
        for key in keys:
            value = _number(gpu.get(key))
            if value is not None:
                values.append(value)
                break
    return values


def worker_gpu_temperature(worker: dict[str, Any]) -> float | None:
    """Return the highest GPU core temperature."""
    values = _gpu_values(worker, "temp", "temperature", "core_temp")
    return max(values) if values else None


def worker_gpu_memory_temperature(worker: dict[str, Any]) -> float | None:
    """Return the highest GPU memory temperature."""
    values = _gpu_values(
        worker, "memtemp", "mem_temp", "memory_temp", "mtemp"
    )
    return max(values) if values else None


def worker_fan_speed(worker: dict[str, Any]) -> float | None:
    """Return average GPU fan speed as a percentage."""
    values = _gpu_values(worker, "fan", "fan_speed")
    return round(sum(values) / len(values), 1) if values else None


def worker_load_average(worker: dict[str, Any]) -> float | None:
    """Return the one-minute system load average."""
    for path in (
        ("hardware_stats", "cpuavg"),
        ("stats", "loadavg"),
        ("stats", "load_average"),
        ("loadavg",),
    ):
        value = _nested_value(worker, *path)
        if isinstance(value, (list, tuple)) and value:
            value = value[0]
        number = _number(value)
        if number is not None:
            return number
    return None


def worker_uptime(worker: dict[str, Any]) -> int | None:
    """Return worker uptime in seconds."""
    value = _first_number(
        worker,
        ("uptime",),
        ("stats", "uptime"),
        ("stats", "miner_uptime"),
    )
    if value is not None:
        return max(0, int(value))
    boot_time = _first_number(worker, ("stats", "boot_time"), ("boot_time",))
    if boot_time is not None:
        return max(0, int(time.time() - boot_time))
    return None


def _hashrate_source(worker: dict[str, Any]) -> Any:
    """Return the first populated HiveOS hashrate collection."""
    for path in (
        ("miners_summary", "hashrates"),
        ("miners_stats", "hashrates"),
        ("hashrates",),
    ):
        value = _nested_value(worker, *path)
        if value:
            return value
    return None


def _hashrate_entries(worker: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized hashrate entries for a worker."""
    value = _hashrate_source(worker)
    if isinstance(value, dict) and any(
        key in value for key in ("hash", "hashrate", "hashrate_value", "value")
    ):
        return [value]
    return _object_list(value)


def worker_hashrates(worker: dict[str, Any]) -> dict[str, float]:
    """Return hashrates grouped by algorithm or coin."""
    totals: dict[str, float] = {}
    source = _hashrate_source(worker)
    if isinstance(source, dict) and not _hashrate_entries(worker):
        for key, value in source.items():
            number = _number(value)
            if number is not None:
                totals[str(key).lower()] = number
        return totals

    for item in _hashrate_entries(worker):
        name = item.get("algo") or item.get("algorithm") or item.get("coin")
        number = next(
            (
                parsed
                for key in ("hash", "hashrate", "hashrate_value", "value")
                if (parsed := _number(item.get(key))) is not None
            ),
            None,
        )
        if name and number is not None:
            label = str(name).lower()
            totals[label] = totals.get(label, 0.0) + number

        dual_name = item.get("dalgo") or item.get("dcoin")
        dual_hashrate = _number(item.get("dhash"))
        if dual_name and dual_hashrate is not None:
            label = str(dual_name).lower()
            totals[label] = totals.get(label, 0.0) + dual_hashrate
    return totals


def worker_active_miners(worker: dict[str, Any]) -> tuple[str, ...]:
    """Return the unique miners currently reporting hashrate data."""
    miners: list[str] = []
    for item in _hashrate_entries(worker):
        miner = item.get("miner")
        if isinstance(miner, str) and miner and miner not in miners:
            miners.append(miner)
    return tuple(miners)


def worker_shares(worker: dict[str, Any]) -> dict[str, int]:
    """Return accepted, rejected, and invalid shares for a worker."""
    totals = {"accepted": 0, "rejected": 0, "invalid": 0}
    found = False
    for item in _hashrate_entries(worker):
        shares = item.get("shares")
        if not isinstance(shares, dict):
            continue
        for key in totals:
            value = _number(shares.get(key))
            if value is not None:
                totals[key] += int(value)
                found = True
    return totals if found else {}


def worker_model(worker: dict[str, Any]) -> str:
    """Return a useful Home Assistant device model."""
    platform = worker.get("platform")
    if isinstance(platform, dict):
        platform = platform.get("name") or platform.get("code")
    if platform in (1, "1"):
        return "GPU rig"
    if platform in (2, "2"):
        return "ASIC"
    return str(platform or worker.get("system_type") or "Mining worker")


def worker_software_version(worker: dict[str, Any]) -> str | None:
    """Return HiveOS software version when present."""
    versions = worker.get("versions")
    if isinstance(versions, dict):
        for key in ("hive", "os", "agent"):
            value = versions.get(key)
            if value is not None:
                return str(value)
    value = worker.get("os_name")
    return str(value) if value else None


class HiveOSClient:
    """Read-only HiveOS API client."""

    def __init__(self, session: ClientSession, token: str, farm_id: str) -> None:
        self._session = session
        self._token = token
        self._farm_id = farm_id

    async def _get_json(self, path: str) -> Any:
        try:
            async with self._session.get(
                f"{API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=20,
            ) as response:
                if response.status in (401, 403):
                    raise HiveOSAuthError("Invalid token or insufficient permissions")
                response.raise_for_status()
                return await response.json()
        except HiveOSAuthError:
            raise
        except (ClientError, ClientResponseError, TimeoutError, ValueError) as err:
            raise HiveOSAPIError("Unable to communicate with HiveOS") from err

    async def async_validate(self) -> None:
        """Validate credentials and farm access."""
        await self._get_json(f"/farms/{self._farm_id}")

    async def async_get_workers(self) -> list[dict[str, Any]]:
        """Fetch current workers for the configured farm."""
        payload = await self._get_json(f"/farms/{self._farm_id}/workers")
        return extract_workers(payload)
