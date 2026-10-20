"""Small asynchronous client for the read-only HiveOS API calls we use."""

from __future__ import annotations

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


def worker_is_online(worker: dict[str, Any]) -> bool:
    """Return an online state while tolerating API field variations."""
    if isinstance(worker.get("online"), bool):
        return worker["online"]
    if isinstance(worker.get("is_online"), bool):
        return worker["is_online"]
    return str(worker.get("status", "")).lower() in {"ok", "online", "working"}


def worker_gpu_count(worker: dict[str, Any]) -> int:
    """Return the number of GPUs reported for a worker."""
    for key in ("gpu_count", "gpus_count"):
        value = worker.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    gpus = worker.get("gpus")
    return len(gpus) if isinstance(gpus, list) else 0


def worker_power(worker: dict[str, Any]) -> float:
    """Return worker power in watts, if present."""
    for key in ("power_draw", "power", "watt"):
        value = worker.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    stats = worker.get("stats")
    if isinstance(stats, dict):
        return worker_power(stats)
    return 0.0


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
