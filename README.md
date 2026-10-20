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
- One child device for every GPU, with individual temperature, memory
  temperature, fan, power, core/memory clocks, load, and hashrate sensors
- Active miner software and accepted, rejected, and invalid share counters
- Cloud polling every 60 seconds
- UI configuration with a HiveOS API token and farm ID

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
