from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_component import async_update_entity

async def async_setup_entry(hass, entry, async_add_entities):
    # Create a switch for each journey in the config entry
    departures = entry.options.get("departures") or entry.data.get("departures", [])
    switches = []
    for idx, dep in enumerate(departures):
        from .sensor import build_sensor_unique_id
        unique_id = build_sensor_unique_id(dep, idx)
        switches.append(VasttrafikPauseSwitch(unique_id, dep.get("name"), hass))
    async_add_entities(switches, True)

class VasttrafikPauseSwitch(SwitchEntity):
    def __init__(self, sensor_unique_id, name, hass):
        self._sensor_unique_id = sensor_unique_id
        self._attr_unique_id = f"pause_{sensor_unique_id}"
        self._attr_name = f"Pause {name or sensor_unique_id}"
        self._attr_icon = "mdi:pause-circle"
        self._attr_entity_category = "config"
        self._hass = hass

    @property
    def is_on(self):
        sensor_entity_id = self._find_sensor_entity_id()
        if sensor_entity_id:
            state = self._hass.states.get(sensor_entity_id)
            if state and "paused" in state.attributes:
                return state.attributes["paused"]
        return False

    async def async_turn_on(self, **kwargs):
        await self._call_pause_service(True)

    async def async_turn_off(self, **kwargs):
        await self._call_pause_service(False)

    def _find_sensor_entity_id(self):
        ent_reg = self._hass.helpers.entity_registry.async_get(self._hass)
        for entity in ent_reg.entities.values():
            if entity.unique_id == self._sensor_unique_id:
                return entity.entity_id
        return None

    async def _call_pause_service(self, paused):
        sensor_entity_id = self._find_sensor_entity_id()
        if sensor_entity_id:
            await self._hass.services.async_call(
                "vastraffik_journey",
                "set_pause",
                {"entity_id": sensor_entity_id, "paused": paused},
                blocking=True,
            )
            await async_update_entity(self._hass, sensor_entity_id)
