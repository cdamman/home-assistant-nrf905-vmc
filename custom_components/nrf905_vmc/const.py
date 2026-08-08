"""Constants for the nRF905 VMC integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "nrf905_vmc"

MANUFACTURER = "nRF905"
MODEL = "VMC"

# Internal speed values sent to the device API.
SPEED_LOW = "low"
SPEED_MEDIUM = "medium"
SPEED_HIGH = "high"

# Preset mode labels shown to the user (and forwarded verbatim to Google Home,
# which does not use Home Assistant entity translations). Kept in French on
# purpose so Google Home displays them in French.
PRESET_LOW = "1 - Bas"
PRESET_MEDIUM = "2 - Normal"
PRESET_HIGH = "3 - Fort"
PRESET_MODES = [PRESET_LOW, PRESET_MEDIUM, PRESET_HIGH]

PRESET_TO_SPEED = {
    PRESET_LOW: SPEED_LOW,
    PRESET_MEDIUM: SPEED_MEDIUM,
    PRESET_HIGH: SPEED_HIGH,
}
SPEED_TO_PRESET = {speed: preset for preset, speed in PRESET_TO_SPEED.items()}

# Electrical power draw for each speed, in watts. These are the values of the
# unit this integration was written against; other units differ, so they are
# only defaults and can be changed from the integration options.
DEFAULT_POWER_BY_SPEED = {
    SPEED_LOW: 13.0,
    SPEED_MEDIUM: 28.0,
    SPEED_HIGH: 58.5,
}

# Option keys holding the per-speed power draw.
CONF_POWER_LOW = "power_low"
CONF_POWER_MEDIUM = "power_medium"
CONF_POWER_HIGH = "power_high"

POWER_OPTION_BY_SPEED = {
    SPEED_LOW: CONF_POWER_LOW,
    SPEED_MEDIUM: CONF_POWER_MEDIUM,
    SPEED_HIGH: CONF_POWER_HIGH,
}

# Bounds accepted for a configured power value, in watts.
MIN_POWER_WATTS = 0.0
MAX_POWER_WATTS = 10000.0

# Timer defaults (auto-revert delay applied by the "on" boost command).
DEFAULT_TIMER_MINUTES = 30
MIN_TIMER_MINUTES = 1
MAX_TIMER_MINUTES = 240

# Status is polled from the device.
SCAN_INTERVAL = timedelta(seconds=30)

# Consecutive failed polls tolerated before the entities go unavailable (and an
# error is logged). Below this, the last known state is kept.
MAX_UPDATE_FAILURES = 3
