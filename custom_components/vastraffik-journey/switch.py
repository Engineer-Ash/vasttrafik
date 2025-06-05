from homeassistant.components.switch import SwitchEntity
from .sensor import VasttrafikJourneySensor

async def async_setup_entry(hass, entry, async_add_entities):
    # Wait for sensors to be registered in hass.data
    sensors = hass.data.get("vastraffik_journey_sensors", [])
    switches = [VasttrafikPauseSwitch(sensor) for sensor in sensors if isinstance(sensor, VasttrafikJourneySensor)]
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
