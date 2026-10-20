"""Tests for the HiveOS API helpers."""

from custom_components.hiveos_monitor.api import (
    extract_workers,
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


def test_worker_mining_details_support_hiveos_shape() -> None:
    worker = {
        "miners_summary": {
            "hashrates": [
                {
                    "miner": "teamredminer",
                    "ver": "0.10.21",
                    "algo": "kheavyhash",
                    "hash": 12_345.5,
                    "dalgo": "zil",
                    "dhash": 456.0,
                    "shares": {
                        "accepted": 120,
                        "rejected": 3,
                        "invalid": 1,
                        "ratio": 97.0,
                    },
                },
                {
                    "miner": "xmrig",
                    "algo": "randomx",
                    "hash": 987.5,
                    "shares": {"accepted": 40, "rejected": 2, "invalid": 0},
                },
            ]
        },
        "miners_stats": {
            "hashrates": [
                {"miner": "duplicate", "algo": "ignored", "hash": 999}
            ]
        },
    }

    assert worker_hashrates(worker) == {
        "kheavyhash": 12_345.5,
        "zil": 456.0,
        "randomx": 987.5,
    }
    assert worker_active_miners(worker) == ("teamredminer", "xmrig")
    assert worker_shares(worker) == {
        "accepted": 160,
        "rejected": 5,
        "invalid": 1,
    }


def test_worker_without_mining_data_is_safe() -> None:
    assert worker_hashrates({}) == {}
    assert worker_active_miners({}) == ()
    assert worker_shares({}) == {}


def test_hardware_stats_fields_used_by_hiveos() -> None:
    worker = {
        "platform": 1,
        "hardware_stats": {
            "cpuavg": [1.25, 0.9, 0.75],
            "cputemp": [48, 55, 51],
        },
        "gpu_stats": [
            {"memtemp": 82},
            {"memtemp": 76},
            {"memtemp": 90},
        ],
    }

    assert worker_load_average(worker) == 1.25
    assert worker_cpu_temperature(worker) == 55
    assert worker_gpu_memory_temperature(worker) == 90
    assert worker_model(worker) == "GPU rig"


def test_asic_platform_has_readable_model() -> None:
    assert worker_model({"platform": 2}) == "ASIC"


def test_worker_gpus_match_stats_and_hashrates_by_bus() -> None:
    worker = {
        "gpu_info": [
            {
                "index": 0,
                "bus_id": "01:00.0",
                "bus_number": 1,
                "brand": "nvidia",
                "model": "GeForce RTX 3070",
                "short_name": "RTX 3070",
            },
            {
                "index": 1,
                "bus_id": "02:00.0",
                "bus_number": 2,
                "brand": "amd",
                "model": "Radeon RX 6600",
                "short_name": "RX 6600",
            },
        ],
        "gpu_stats": [
            {
                "bus_number": 2,
                "temp": 58,
                "memtemp": 72,
                "fan": 65,
                "power": 71,
                "coreclk": 950,
                "memclk": 950,
                "load": 99,
            },
            {
                "bus_number": 1,
                "temp": 55,
                "memtemp": 68,
                "fan": 60,
                "power": 120,
                "coreclk": 1100,
                "memclk": 2100,
                "load": 98,
            },
        ],
        "miners_summary": {
            "hashrates": [
                {
                    "algo": "kheavyhash",
                    "hashes": [101.5, 202.5],
                    "bus_numbers": [1, 2],
                    "dalgo": "zil",
                    "dhashes": [11.0, 22.0],
                    "dbus_numbers": [1, 2],
                }
            ]
        },
    }

    gpus = worker_gpus(worker)

    assert [gpu["id"] for gpu in gpus] == ["01:00.0", "02:00.0"]
    assert gpus[0]["temp"] == 55
    assert gpus[0]["memtemp"] == 68
    assert gpus[0]["hashrates"] == {"kheavyhash": 101.5, "zil": 11.0}
    assert gpus[1]["temp"] == 58
    assert gpus[1]["power"] == 71
    assert gpus[1]["hashrates"] == {"kheavyhash": 202.5, "zil": 22.0}


def test_worker_gpus_fall_back_to_list_order() -> None:
    worker = {
        "gpu_info": [{"index": 0}, {"index": 1}],
        "gpu_stats": [{"temp": 50}, {"temp": 60}],
        "miners_summary": {
            "hashrates": [{"algo": "randomx", "hashes": [123, 456]}]
        },
    }

    gpus = worker_gpus(worker)

    assert gpus[0]["temp"] == 50
    assert gpus[0]["hashrates"] == {"randomx": 123}
    assert gpus[1]["temp"] == 60
    assert gpus[1]["hashrates"] == {"randomx": 456}
