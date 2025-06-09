from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers import entity_registry as er
import logging
from .sensor import build_sensor_unique_id, CONF_DEPARTURES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    # Use the correct key for departures
    departures = entry.options.get(CONF_DEPARTURES) or entry.data.get(CONF_DEPARTURES, [])
    if not departures:
        _LOGGER.info("No switches created: departures list was empty or not found.")
        async_add_entities([], True)
        return
    _LOGGER.debug(f"Setting up switches for departures: {departures}")
    switches = []
    for idx, dep in enumerate(departures):
        unique_id = build_sensor_unique_id(dep, idx)
        _LOGGER.debug(f"Creating switch for journey idx={idx}, unique_id={unique_id}, dep={dep}")
        switches.append(VasttrafikPauseSwitch(unique_id, dep.get("name"), hass))
    async_add_entities(switches, True)

class VasttrafikPauseSwitch(SwitchEntity):
    def __init__(self, sensor_unique_id, name, hass):
        self._sensor_unique_id = sensor_unique_id
        self._attr_unique_id = f"pause_{sensor_unique_id}"
        self._attr_name = f"Pause {name or sensor_unique_id}"
        self._attr_icon = "mdi:pause-circle"
        self._attr_entity_category = EntityCategory.CONFIG
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
        ent_reg = er.async_get(self._hass)
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

    @property
    def entity_category(self):
        return EntityCategory.CONFIG
