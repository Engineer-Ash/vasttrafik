from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_component import async_update_entity

async def async_setup_entry(hass, entry, async_add_entities):
    # Get all journey sensor entity_ids for this config entry from entity registry
    entity_registry = await hass.helpers.entity_registry.async_get_registry()
    sensor_entity_ids = [entity.entity_id for entity in entity_registry.entities.values()
                        if entity.domain == 'sensor' and entity.config_entry_id == entry.entry_id]
    switches = [VasttrafikPauseSwitch(entity_id) for entity_id in sensor_entity_ids]
    async_add_entities(switches, True)

class VasttrafikPauseSwitch(SwitchEntity):
    """Switch to pause/unpause a VasttrafikJourneySensor by entity_id."""
    def __init__(self, sensor_entity_id):
        self._sensor_entity_id = sensor_entity_id
        self._attr_unique_id = f"pause_{sensor_entity_id.replace('.', '_')}"
        self._attr_name = f"Pause {sensor_entity_id.split('.')[-1].replace('_', ' ').title()}"
        self._attr_icon = "mdi:pause-circle"
        self._attr_entity_category = "config"
        self._hass = None

    async def async_added_to_hass(self):
        self._hass = self.hass

    @property
    def is_on(self):
        # Read the paused attribute from the sensor's state
        state = self._hass.states.get(self._sensor_entity_id)
        if state and 'paused' in state.attributes:
            return state.attributes['paused']
        return False

    async def async_turn_on(self, **kwargs):
        # Call the custom pause service to pause the sensor
        await self._hass.services.async_call(
            "vastraffik_journey", "set_pause",
            {"entity_id": self._sensor_entity_id, "paused": True},
            blocking=True
        )
        await async_update_entity(self._hass, self._sensor_entity_id)

    async def async_turn_off(self, **kwargs):
        # Call the custom pause service to unpause the sensor
        await self._hass.services.async_call(
            "vastraffik_journey", "set_pause",
            {"entity_id": self._sensor_entity_id, "paused": False},
            blocking=True
        )
        await async_update_entity(self._hass, self._sensor_entity_id)
