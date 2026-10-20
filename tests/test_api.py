"""Tests for the HiveOS API helpers."""

from custom_components.hiveos_monitor.api import (
    extract_workers,
    worker_gpu_count,
    worker_is_online,
    worker_power,
)


def test_extract_workers_from_nested_data() -> None:
    workers = [{"id": 1}, {"id": 2}]
    assert extract_workers({"data": {"workers": workers}}) == workers


def test_worker_helpers_accept_common_shapes() -> None:
    worker = {
        "status": "online",
        "gpus": [{"name": "A"}, {"name": "B"}],
        "stats": {"power": 245.5},
    }
    assert worker_is_online(worker) is True
    assert worker_gpu_count(worker) == 2
    assert worker_power(worker) == 245.5


def test_unknown_payload_is_safe() -> None:
    assert extract_workers({"data": None}) == []
    assert worker_is_online({}) is False
    assert worker_gpu_count({}) == 0
    assert worker_power({}) == 0.0
