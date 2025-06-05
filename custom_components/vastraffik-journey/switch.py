from homeassistant.components.switch import SwitchEntity
from .sensor import VasttrafikJourneySensor

async def async_setup_entry(hass, entry, async_add_entities):
    # Find all journey sensors and create switches for them
    sensors = [entity for entity in hass.data.get("vastraffik_journey_sensors", []) if isinstance(entity, VasttrafikJourneySensor)]
    switches = [VasttrafikPauseSwitch(sensor) for sensor in sensors]
    async_add_entities(switches, True)

class VasttrafikPauseSwitch(SwitchEntity):
    """Switch to pause/unpause a VasttrafikJourneySensor."""
    def __init__(self, sensor: VasttrafikJourneySensor):
        self._sensor = sensor
        self._attr_unique_id = f"pause_{sensor._attr_unique_id}"
    @property
    def name(self):
        return f"Pause {self._sensor.name}"
    @property
    def is_on(self):
        return self._sensor._paused
    async def async_turn_on(self, **kwargs):
        self._sensor.set_paused(True)
    async def async_turn_off(self, **kwargs):
        self._sensor.set_paused(False)
