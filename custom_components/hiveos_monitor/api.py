"""Small asynchronous client for the read-only HiveOS API calls we use."""

from __future__ import annotations

import math
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
    return _first_number(
        worker,
        ("cpu_temp",),
        ("stats", "cpu_temp"),
        ("hardware_stats", "cpu_temp"),
    )


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
    values = _gpu_values(worker, "mem_temp", "memory_temp", "mtemp")
    return max(values) if values else None


def worker_fan_speed(worker: dict[str, Any]) -> float | None:
    """Return average GPU fan speed as a percentage."""
    values = _gpu_values(worker, "fan", "fan_speed")
    return round(sum(values) / len(values), 1) if values else None


def worker_load_average(worker: dict[str, Any]) -> float | None:
    """Return the one-minute system load average."""
    for path in (("stats", "loadavg"), ("stats", "load_average"), ("loadavg",)):
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
    return max(0, int(value)) if value is not None else None


def worker_hashrates(worker: dict[str, Any]) -> dict[str, float]:
    """Return hashrates grouped by algorithm or coin."""
    totals: dict[str, float] = {}

    def add_items(value: Any) -> None:
        if isinstance(value, dict):
            if any(key in value for key in ("hashrate", "hashrate_value", "value")):
                items = [value]
            else:
                for key, item in value.items():
                    number = _number(item)
                    if number is not None:
                        totals[str(key)] = totals.get(str(key), 0.0) + number
                items = _object_list(value)
        else:
            items = _object_list(value)
        for item in items:
            name = item.get("algo") or item.get("algorithm") or item.get("coin")
            number = next(
                (
                    parsed
                    for key in ("hashrate", "hashrate_value", "value")
                    if (parsed := _number(item.get(key))) is not None
                ),
                None,
            )
            if name and number is not None:
                label = str(name).lower()
                totals[label] = totals.get(label, 0.0) + number

    for path in (
        ("miners_summary", "hashrates"),
        ("miners_stats", "hashrates"),
        ("hashrates",),
    ):
        add_items(_nested_value(worker, *path))
    return totals


def worker_model(worker: dict[str, Any]) -> str:
    """Return a useful Home Assistant device model."""
    platform = worker.get("platform")
    if isinstance(platform, dict):
        platform = platform.get("name") or platform.get("code")
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
