from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_component import async_update_entity
from .sensor import VasttrafikJourneySensor

async def async_setup_entry(hass, entry, async_add_entities):
    # Use sensors stored in hass.data by the sensor platform
    sensors = hass.data.get("vastraffik_journey_sensors", [])
    switches = [VasttrafikPauseSwitch(sensor, hass) for sensor in sensors if isinstance(sensor, VasttrafikJourneySensor)]
    async_add_entities(switches, True)

class VasttrafikPauseSwitch(SwitchEntity):
    """Switch to pause/unpause a VasttrafikJourneySensor."""
    def __init__(self, sensor: VasttrafikJourneySensor, hass):
        self._sensor = sensor
        self._hass = hass
        self._attr_unique_id = f"pause_{sensor._attr_unique_id}"
        self._attr_name = f"Pause {sensor.name}"
        self._attr_icon = "mdi:pause-circle"
        self._attr_entity_category = "config"

    @property
    def is_on(self):
        return self._sensor._paused

    async def async_turn_on(self, **kwargs):
        self._sensor.set_paused(True)
        await async_update_entity(self._hass, self._sensor.entity_id)

    async def async_turn_off(self, **kwargs):
        self._sensor.set_paused(False)
        await async_update_entity(self._hass, self._sensor.entity_id)
