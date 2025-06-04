"""Vasttrafik component."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from typing import Any


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Västtrafik component from YAML."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Västtrafik from a config entry (UI)."""
    # Ensure required values are present before starting sensor
    if not entry.data.get("key") or not entry.data.get("secret"):
        hass.helpers.logger.error(
            "Västtrafik config entry missing key or secret. Sensor setup aborted."
        )
        return False
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")
