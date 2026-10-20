# HiveOS Monitor

Custom Home Assistant integration for read-only monitoring of a HiveOS farm.

## Features

- Total, online, and offline worker counts
- GPU count
- Farm power consumption
- One Home Assistant device for every HiveOS worker
- Per-worker status, power, GPU count, CPU/GPU temperatures, fan speed,
  load average, and uptime
- Per-worker hashrate sensors, discovered dynamically for each algorithm
- Active miner software and accepted, rejected, and invalid share counters
- Cloud polling every 60 seconds
- UI configuration with a HiveOS API token and farm ID

### Individual GPU monitoring

Starting with version 0.4.0, every GPU is represented as a separate Home
Assistant device below its HiveOS worker. Each GPU can expose:

- Core temperature
- Memory temperature
- Fan speed
- Power consumption
- Core clock
- Memory clock
- GPU load
- A separate hashrate sensor for every algorithm reported by HiveOS,
  including dual-mining algorithms

GPU information and live statistics are matched through the PCI bus whenever
HiveOS supplies it. This keeps devices and entity IDs stable even if the API
returns hardware information and statistics in a different order. The GPU
model and manufacturer are also shown in the Home Assistant device page.

The integration keeps the existing farm-wide and per-worker aggregate sensors,
so dashboards and automations created with earlier versions continue to work.
Some cards can show an entity as unavailable when the GPU, driver, or miner does
not report that particular metric to HiveOS. In particular, GPU load is not part
of every HiveOS cloud API response, and memory temperature is unavailable on
many GPU/driver combinations.

### Device hierarchy

Home Assistant organizes the integration as follows:

- HiveOS farm
  - Worker
    - GPU 0
    - GPU 1
    - Additional GPUs reported by the worker

## Installation

1. In HACS, add this repository as a custom repository with category **Integration**.
2. Install **HiveOS Monitor** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and select **HiveOS Monitor**.
4. Enter a read-only HiveOS API token and the numeric farm ID.

The token is stored by Home Assistant in the config entry. It is never written to logs or repository files.

## Manual installation

Copy `custom_components/hiveos_monitor` into the `custom_components` directory of your Home Assistant configuration, then restart Home Assistant.

## Notes

HiveOS API access may depend on the account or farm plan. This integration only performs `GET` requests.

## Support the project

If this integration is useful to you, you can [support its development with an optional cryptocurrency donation](DONATE.md). Donations do not unlock features or affect support.

## License

MIT
