"""Constants for HiveOS Monitor."""

from datetime import timedelta

DOMAIN = "hiveos_monitor"
CONF_API_TOKEN = "api_token"
CONF_FARM_ID = "farm_id"
API_BASE_URL = "https://api2.hiveos.farm/api/v2"
SCAN_INTERVAL = timedelta(seconds=60)
