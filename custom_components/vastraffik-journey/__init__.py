"""Vastraffik Journey component."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from typing import Any


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Vastraffik Journey component from YAML."""
    # Allow YAML configuration for client id/secret
    if config.get("vastraffik_journey"):
        hass.data.setdefault("vastraffik_journey", {})
        hass.data["vastraffik_journey"]["yaml_config"] = config["vastraffik_journey"]
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vastraffik Journey from a config entry (UI)."""
    # Ensure required values are present before starting sensor
    if not entry.data.get("client_id") or not entry.data.get("secret"):
        hass.helpers.logger.error(
            "Vastraffik Journey config entry missing client_id or secret. Sensor setup aborted."
        )
        return False
    # Add update listener to reload on options change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "switch"])
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Reload when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    unload_ok_switch = await hass.config_entries.async_forward_entry_unload(entry, "switch")
    return unload_ok and unload_ok_switch
