"""Vastraffik Journey component."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from typing import Any
from homeassistant.helpers.entity import Entity
import logging
import traceback


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    try:
        """Set up the Vastraffik Journey component from YAML."""
        # Allow YAML configuration for client id/secret
        if config.get("vastraffik_journey"):
            hass.data.setdefault("vastraffik_journey", {})
            hass.data["vastraffik_journey"]["yaml_config"] = config["vastraffik_journey"]
        # Register the pause service globally
        async def handle_pause_service(call):
            entity_id = call.data.get("entity_id")
            paused = call.data.get("paused")
            toggle = call.data.get("toggle", False)
            # Find the entity and call set_paused or toggle_paused
            entity: Entity = None
            for ent in hass.states.async_entity_ids("sensor"):
                ent_obj = hass.data.get("entity_components", {}).get("sensor", None)
                if ent_obj:
                    entity = ent_obj.get_entity(ent)
                    if entity and entity.entity_id == entity_id:
                        break
            if entity:
                if toggle:
                    entity.toggle_paused()
                elif paused is not None:
                    entity.set_paused(paused)
                entity.async_write_ha_state()
        hass.services.async_register(
            "vastraffik_journey",
            "set_pause",
            handle_pause_service,
            schema=None,
        )
        return True
    except Exception as ex:
        logging.getLogger(__name__).error("Exception in async_setup: %s\n%s", ex, traceback.format_exc())
        return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
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
    except Exception as ex:
        logging.getLogger(__name__).error("Exception in async_setup_entry: %s\n%s", ex, traceback.format_exc())
        return False


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Reload when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
        unload_ok_switch = await hass.config_entries.async_forward_entry_unload(entry, "switch")
        return unload_ok and unload_ok_switch
    except Exception as ex:
        logging.getLogger(__name__).error("Exception in async_unload_entry: %s\n%s", ex, traceback.format_exc())
        return False
