"""Constants for the TR7 Exalus Local integration."""

from typing import Final

DOMAIN: Final = "tr7_exalus_local"

# Config Flow
DEFAULT_PORT: Final = 81
DEFAULT_NAME: Final = "TR7 Exalus"
CONF_SERIAL_NUMBER: Final = "serial_number"
CONF_PIN: Final = "pin"

UPDATE_INTERVAL: Final = 30  # seconds

# Proactively re-login before the TR7 can expire its session. The controller
# appears to drop the authenticated session after ~24 h regardless of activity,
# so renewing well under that avoids ever hitting a dead-session window.
SESSION_RENEW_INTERVAL: Final = 12 * 60 * 60  # 12 hours, in seconds

# Device States
STATE_IDLE: Final = "idle"
STATE_OPENING: Final = "opening"
STATE_CLOSING: Final = "closing"
STATE_STOPPED: Final = "stopped"
STATE_ERROR: Final = "error"

# Attribute Keys
ATTR_DEVICE_GUID: Final = "device_guid"
ATTR_STATE: Final = "state"
ATTR_BATTERY_LEVEL: Final = "battery_level"
ATTR_SIGNAL_STRENGTH: Final = "signal_strength"
ATTR_SIGNAL_QUALITY: Final = "signal_quality"
ATTR_LAST_TASK_SUCCEEDED: Final = "last_task_succeeded"
ATTR_OPEN_TIME: Final = "open_time"
ATTR_CLOSE_TIME: Final = "close_time"
ATTR_CALIBRATION_STATUS: Final = "calibration_status"
ATTR_FIRMWARE: Final = "firmware"
ATTR_LAST_SEEN: Final = "last_seen"
