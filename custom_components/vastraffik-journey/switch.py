from homeassistant.components.switch import SwitchEntity
from .sensor import CONF_CLIENT_ID, CONF_SECRET, CONF_DEPARTURES, CONF_FROM, CONF_DESTINATION, CONF_LINES, CONF_DELAY, CONF_NAME, VasttrafikJourneySensor
from vasttrafik import JournyPlanner
from datetime import timedelta

async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.data
    options = entry.options
    departures = options.get(CONF_DEPARTURES)
    if departures is None:
        departures = data.get(CONF_DEPARTURES)
    if not departures:
        return
    planner = JournyPlanner(data[CONF_CLIENT_ID], data[CONF_SECRET])
    switches = []
    for idx, departure in enumerate(departures):
        # Use the same unique_id logic as the sensor
        origin = departure.get(CONF_FROM)
        destination = departure.get(CONF_DESTINATION)
        lines = departure.get(CONF_LINES)
        delay = departure.get(CONF_DELAY)
        name = departure.get(CONF_NAME)
        sensor = VasttrafikJourneySensor(
            planner,
            name,
            origin,
            destination,
            lines,
            delay,
            index=idx
        )
        switches.append(VasttrafikPauseSwitch(sensor))
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
