"""Support for Västtrafik public transport."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import logging

from vasttrafik import JournyPlanner, Error
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorEntity,
)
from homeassistant.const import CONF_DELAY, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle
from homeassistant.util.dt import now

_LOGGER = logging.getLogger(__name__)

ATTR_ACCESSIBILITY = "accessibility"
ATTR_DIRECTION = "direction"
ATTR_LINE = "line"
ATTR_TRACK = "track"
ATTR_FROM = "from"
ATTR_TO = "to"
ATTR_DELAY = "delay"

CONF_DEPARTURES = "departures"
CONF_FROM = "from"
CONF_DESTINATION = "destination"
CONF_HEADING = "heading"
CONF_LINES = "lines"
CONF_CLIENT_ID = "client_id"
CONF_SECRET = "secret"

DEFAULT_DELAY = 0

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=120)

PLATFORM_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_SECRET): cv.string,
        vol.Required(CONF_DEPARTURES): vol.All(
            [
                {
                    vol.Required(CONF_FROM): cv.string,
                    vol.Required(CONF_DESTINATION): cv.string,
                    vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): cv.positive_int,
                    vol.Optional(CONF_HEADING): cv.string,
                    vol.Optional(CONF_LINES, default=[]): vol.All(
                        cv.ensure_list, [cv.string]
                    ),
                    vol.Optional(CONF_NAME): cv.string,
                    vol.Optional("pause_entity_id"): cv.string,
                }
            ]
        ),
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the journey sensor from YAML."""
    planner = JournyPlanner(config.get(CONF_CLIENT_ID), config.get(CONF_SECRET))
    sensors = []
    for idx, departure in enumerate(config[CONF_DEPARTURES]):
        sensor = VasttrafikJourneySensor(
            planner,
            departure.get(CONF_NAME),
            departure.get(CONF_FROM),
            departure.get(CONF_DESTINATION),
            departure.get(CONF_LINES),
            departure.get(CONF_DELAY),
            departure.get("pause_entity_id"),
            index=idx,  # Pass index to sensor
        )
        sensors.append(sensor)
    async_add_entities(sensors, True)

    async def handle_pause_service(call):
        entity_id = call.data.get("entity_id")
        paused = call.data.get("paused")
        toggle = call.data.get("toggle", False)
        for sensor in sensors:
            if sensor.entity_id == entity_id:
                if toggle:
                    sensor.toggle_paused()
                elif paused is not None:
                    sensor.set_paused(paused)

    hass.services.async_register(
        "vastraffik_journey",
        "set_pause",
        handle_pause_service,
        schema=vol.Schema(
            {
                vol.Required("entity_id"): cv.entity_id,
                vol.Optional("paused"): bool,
                vol.Optional("toggle", default=False): bool,
            }
        ),
    )


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Legacy sync setup for backward compatibility."""
    hass.async_create_task(
        async_setup_platform(hass, config, add_entities, discovery_info)
    )


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up the journey sensor from a config entry (UI)."""
    data = entry.data
    options = entry.options
    departures = options.get(CONF_DEPARTURES)
    if departures is None:
        departures = data.get(CONF_DEPARTURES)
    if not departures:
        _LOGGER.info("No departures found in config entry data or options: %s", {**data, **options})
        return

    def create_sensors():
        planner = JournyPlanner(data[CONF_CLIENT_ID], data[CONF_SECRET])
        sensors = []
        for idx, departure in enumerate(departures):
            sensor = VasttrafikJourneySensor(
                planner,
                departure.get(CONF_NAME),
                departure.get(CONF_FROM),
                departure.get(CONF_DESTINATION),
                departure.get(CONF_LINES),
                departure.get(CONF_DELAY),
                departure.get("pause_entity_id"),
                index=idx,  # Pass index to sensor
            )
            sensors.append(sensor)
        return sensors

    sensors = await hass.async_add_executor_job(create_sensors)
    async_add_entities(sensors, True)
    # Store sensors in hass.data for switch platform
    hass.data.setdefault("vastraffik_journey_sensors", []).extend(sensors)


class VasttrafikJourneySensor(SensorEntity):
    """Implementation of a Vasttrafik Journey Sensor."""

    _attr_attribution = "Data provided by Västtrafik"
    _attr_icon = "mdi:train"

    def __init__(self, planner, name, origin, destination, lines, delay, pause_entity_id=None, index=None):
        """Initialize the sensor."""
        self._planner = planner
        # Use index-based name if no custom name is provided
        if name:
            self._name = name
        elif index is not None:
            self._name = f"Journey {index + 1}"
        else:
            self._name = f"{origin} to {destination}"
        self._origin = self.get_station_id(origin)
        self._destination = self.get_station_id(destination)
        self._lines = lines if lines else None
        self._delay = timedelta(minutes=delay)
        self._journeys = None
        self._state = None
        self._attributes = None
        self._pause_entity_id = pause_entity_id
        self._paused = False  # Internal pause state
        self.hass = None  # Will be set in async_added_to_hass
        unique = f"{self._origin['station_id']}_{self._destination['station_id']}_{','.join(self._lines) if self._lines else ''}"
        self._attr_unique_id = hashlib.md5(unique.encode()).hexdigest()

    async def async_added_to_hass(self):
        self.hass = self._hass if hasattr(self, '_hass') else getattr(self, 'hass', None) or self.hass
        if self.hass is None:
            self.hass = self._hass = getattr(self, 'hass', None)

    def get_station_id(self, location):
        """Get the station ID."""
        if location.isdecimal():
            station_info = {"station_name": location, "station_id": location}
        else:
            station_id = self._planner.location_name(location)[0]["gid"]
            station_info = {"station_name": location, "station_id": station_id}
        return station_info

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = self._attributes.copy() if self._attributes else {}
        attrs["paused"] = self._paused
        return attrs

    @property
    def native_value(self):
        """Return the next journey departure time."""
        return self._state

    def set_paused(self, paused: bool):
        self._paused = paused
        self.async_write_ha_state()

    def toggle_paused(self):
        self._paused = not self._paused
        self.async_write_ha_state()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self) -> None:
        """Get the next journey."""
        if self._paused:
            _LOGGER.debug(f"Update paused for {self._name} due to internal pause attribute.")
            return
        try:
            self._journeys = self._planner.trip(
                origin_id=self._origin["station_id"],
                dest_id=self._destination["station_id"],
                date=now() + self._delay,
            )
        except Error:
            _LOGGER.debug("Unable to read journeys, updating token")
            self._planner.update_token()

        if not self._journeys:
            _LOGGER.debug(
                "No journeys from %s to %s",
                self._origin["station_name"],
                self._destination["station_name"],
            )
            self._state = None
            self._attributes = {}
        else:
            def extract_stop_name(endpoint):
                if isinstance(endpoint, dict):
                    if "name" in endpoint:
                        return endpoint["name"]
                    if "stopPoint" in endpoint and "name" in endpoint["stopPoint"]:
                        return endpoint["stopPoint"]["name"]
                return str(endpoint) if endpoint else "?"

            for journey in self._journeys:
                legs = journey.get("tripLegs", [])
                if not legs:
                    continue
                main_leg = next((l for l in legs if l.get("serviceJourney")), legs[0])
                service_journey = main_leg.get("serviceJourney", {})
                line = service_journey.get("line", {})
                if not self._lines or line.get("shortName") in self._lines:
                    dep_time = main_leg.get("plannedDepartureTime")
                    arr_time = main_leg.get("plannedArrivalTime")
                    try:
                        self._state = datetime.fromisoformat(dep_time).strftime("%H:%M")
                    except Exception:
                        self._state = dep_time

                    connections = []
                    for idx, leg in enumerate(legs, 1):
                        sj = leg.get("serviceJourney", {})
                        line = sj.get("line", {})
                        line_name = line.get("shortName") or line.get("name") or "?"
                        from_endpoint = leg.get("origin") or leg.get("from") or {}
                        to_endpoint = leg.get("destination") or leg.get("to") or {}
                        from_name = extract_stop_name(from_endpoint)
                        to_name = extract_stop_name(to_endpoint)
                        if from_name == "?" or to_name == "?":
                            _LOGGER.debug(f"Leg missing stop name: {leg}")
                        dep = leg.get("plannedDepartureTime")
                        arr = leg.get("plannedArrivalTime")
                        dep_fmt = dep[11:16] if dep and len(dep) >= 16 else dep
                        arr_fmt = arr[11:16] if arr and len(arr) >= 16 else arr
                        connections.append(f"{idx}. {line_name} from {from_name} to {to_name} ({dep_fmt} → {arr_fmt})")
                    connections_str = "\n".join(connections)

                    final_arrival = legs[-1].get("plannedArrivalTime") if legs else None
                    try:
                        final_arrival_fmt = datetime.fromisoformat(final_arrival).strftime("%H:%M") if final_arrival else None
                    except Exception:
                        final_arrival_fmt = final_arrival

                    params = {
                        ATTR_LINE: line.get("shortName"),
                        ATTR_FROM: self._origin["station_name"],
                        ATTR_TO: self._destination["station_name"],
                        "planned_arrival": arr_time,
                        "direction": service_journey.get("direction"),
                        "connections": connections_str,
                        "final_arrival": final_arrival_fmt,
                    }
                    self._attributes = {k: v for k, v in params.items() if v}
                    break