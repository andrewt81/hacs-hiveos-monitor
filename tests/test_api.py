"""Tests for the HiveOS API helpers."""

from custom_components.hiveos_monitor.api import (
    extract_workers,
    worker_cpu_temperature,
    worker_fan_speed,
    worker_gpu_count,
    worker_gpu_memory_temperature,
    worker_gpu_temperature,
    worker_hashrates,
    worker_id,
    worker_is_online,
    worker_load_average,
    worker_name,
    worker_power,
    worker_uptime,
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
    assert worker_power({}) is None


def test_worker_helpers_support_hiveos_nested_shape() -> None:
    worker = {
        "id": 42,
        "name": "rig-alpha",
        "stats": {
            "online": True,
            "cpu_temp": 61,
            "loadavg": [0.42, 0.35, 0.2],
            "uptime": 7200,
        },
        "gpu_summary": {"gpus": 2, "power_draw": 315},
        "gpu_stats": [
            {"temp": 55, "mem_temp": 78, "fan": 60},
            {"temp": 63, "mem_temp": 82, "fan": 70},
        ],
        "miners_summary": {
            "hashrates": [
                {"algo": "kheavyhash", "hashrate": 1_000_000},
                {"algo": "kheavyhash", "hashrate": 2_000_000},
                {"coin": "xmr", "value": "1234.5"},
            ]
        },
    }

    assert worker_id(worker) == "42"
    assert worker_name(worker) == "rig-alpha"
    assert worker_is_online(worker) is True
    assert worker_gpu_count(worker) == 2
    assert worker_power(worker) == 315
    assert worker_cpu_temperature(worker) == 61
    assert worker_gpu_temperature(worker) == 63
    assert worker_gpu_memory_temperature(worker) == 82
    assert worker_fan_speed(worker) == 65
    assert worker_load_average(worker) == 0.42
    assert worker_uptime(worker) == 7200
    assert worker_hashrates(worker) == {"kheavyhash": 3_000_000, "xmr": 1234.5}


def test_worker_hashrates_support_mapping_shape() -> None:
    worker = {"hashrates": {"ethash": 123.5, "etchash": "456"}}
    assert worker_hashrates(worker) == {"ethash": 123.5, "etchash": 456}
