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

# Preset mode labels shown to the user and forwarded to Google Home.
PRESET_LOW = "low"
PRESET_MEDIUM = "medium"
PRESET_HIGH = "high"
PRESET_MODES = [PRESET_LOW, PRESET_MEDIUM, PRESET_HIGH]

PRESET_TO_SPEED = {
    PRESET_LOW: SPEED_LOW,
    PRESET_MEDIUM: SPEED_MEDIUM,
    PRESET_HIGH: SPEED_HIGH,
}
SPEED_TO_PRESET = {speed: preset for preset, speed in PRESET_TO_SPEED.items()}

# Timer defaults (auto-revert delay applied by the "on" boost command).
DEFAULT_TIMER_MINUTES = 30
MIN_TIMER_MINUTES = 1
MAX_TIMER_MINUTES = 240

# Status is polled from the device.
SCAN_INTERVAL = timedelta(seconds=30)
