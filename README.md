# HiveOS Monitor

Custom Home Assistant integration for read-only monitoring of a HiveOS farm.

## Features

- Total, online, and offline worker counts
- GPU count
- Farm power consumption
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

## License

MIT
