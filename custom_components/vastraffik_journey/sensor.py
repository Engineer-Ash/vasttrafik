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
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

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
CONF_LIST_START_TIME = "list_start_time"
CONF_LIST_END_TIME = "list_end_time"
CONF_LIST_TIME_RELATES_TO = "list_time_relates_to"  # 'departure' or 'arrival'

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
        vol.Optional("journey_list_sensors", default=[]): vol.All(
            [
                {
                    vol.Required(CONF_FROM): cv.string,
                    vol.Required(CONF_DESTINATION): cv.string,
                    vol.Optional(CONF_LINES, default=[]): vol.All(cv.ensure_list, [cv.string]),
                    vol.Optional(CONF_NAME): cv.string,
                    vol.Required(CONF_LIST_START_TIME): cv.string,  # e.g. '06:00'
                    vol.Required(CONF_LIST_END_TIME): cv.string,    # e.g. '09:00'
                    vol.Optional(CONF_LIST_TIME_RELATES_TO, default="departure"): vol.In(["departure", "arrival"]),
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
    # Add journey list sensors
    journey_list_sensors = config.get("journey_list_sensors", [])
    for idx, sensor_conf in enumerate(journey_list_sensors):
        sensor = VasttrafikJourneyListSensor(
            planner,
            sensor_conf.get(CONF_NAME),
            sensor_conf.get(CONF_FROM),
            sensor_conf.get(CONF_DESTINATION),
            sensor_conf.get(CONF_LINES),
            sensor_conf.get(CONF_LIST_START_TIME),
            sensor_conf.get(CONF_LIST_END_TIME),
            sensor_conf.get(CONF_LIST_TIME_RELATES_TO, "departure"),
            index=idx,
        )
        sensors.append(sensor)
    async_add_entities(sensors, True)


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
    journey_list_sensors = options.get("journey_list_sensors", [])
    if departures is None:
        departures = data.get(CONF_DEPARTURES)
    if not departures:
        _LOGGER.info("No departures found in config entry data or options: %s", {**data, **options})
        return

    # --- Remove orphaned sensors and switches for both journey and list sensors ---
    entity_registry = async_get_entity_registry(hass)  # Remove await, this is a synchronous function
    sensor_domain = "sensor"
    switch_domain = "switch"
    # Collect all valid unique_ids for journey and list sensors
    current_sensor_unique_ids = set()
    current_switch_unique_ids = set()
    for idx, dep in enumerate(departures):
        uid = build_sensor_unique_id(dep, idx)
        current_sensor_unique_ids.add(uid)
        current_switch_unique_ids.add(f"pause_{uid}")
    for idx, ls in enumerate(journey_list_sensors):
        # List sensor unique_id format must match VasttrafikJourneyListSensor
        uid = f"journeylist_{ls.get('from')}_{ls.get('destination')}_{ls.get('list_start_time')}_{ls.get('list_end_time')}_{ls.get('list_time_relates_to', 'departure')}_{idx}"
        current_sensor_unique_ids.add(uid)
    # Remove orphaned sensors and their linked pause switches
    for entity in list(entity_registry.entities.values()):
        # Remove orphaned sensors
        if entity.domain == sensor_domain and entity.config_entry_id == entry.entry_id:
            if entity.unique_id not in current_sensor_unique_ids:
                _LOGGER.info(f"Removing orphaned sensor entity: {entity.entity_id} (unique_id={entity.unique_id})")
                entity_registry.async_remove(entity.entity_id)
                # Also remove linked pause switch if it exists
                pause_switch_unique_id = f"pause_{entity.unique_id}"
                for sw_entity in list(entity_registry.entities.values()):
                    if sw_entity.domain == switch_domain and sw_entity.unique_id == pause_switch_unique_id:
                        _LOGGER.info(f"Removing orphaned pause switch: {sw_entity.entity_id} (unique_id={sw_entity.unique_id})")
                        entity_registry.async_remove(sw_entity.entity_id)
        # Remove orphaned pause switches (if their linked sensor is gone)
        if entity.domain == switch_domain and entity.config_entry_id == entry.entry_id:
            linked_sensor_unique_id = entity.unique_id.replace("pause_", "", 1)
            if linked_sensor_unique_id not in current_sensor_unique_ids:
                _LOGGER.info(f"Removing orphaned pause switch (no linked sensor): {entity.entity_id} (unique_id={entity.unique_id})")
                entity_registry.async_remove(entity.entity_id)

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
        for idx, ls in enumerate(journey_list_sensors):
            sensor = VasttrafikJourneyListSensor(
                planner,
                ls.get(CONF_NAME),
                ls.get(CONF_FROM),
                ls.get(CONF_DESTINATION),
                ls.get(CONF_LINES),
                ls.get(CONF_LIST_START_TIME),
                ls.get(CONF_LIST_END_TIME),
                ls.get(CONF_LIST_TIME_RELATES_TO, "departure"),
                index=idx,
            )
            sensors.append(sensor)
        return sensors

    sensors = await hass.async_add_executor_job(create_sensors)
    async_add_entities(sensors, True)
    # Store sensors in hass.data for switch platform
    hass.data.setdefault("vastraffik_journey_sensors", []).extend(sensors)


def build_sensor_unique_id(dep, idx):
    origin = dep.get("from")
    destination = dep.get("destination")
    lines = dep.get("lines") or []
    if not origin or not destination:
        return f"journey_{idx}"
    unique = f"{origin}_{destination}_{','.join(lines) if lines else ''}"
    import hashlib
    return hashlib.md5(unique.encode()).hexdigest()


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
        # Use the helper for unique_id
        dep = {
            "from": origin,
            "destination": destination,
            "lines": lines
        }
        self._attr_unique_id = build_sensor_unique_id(dep, index)

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
        # When pausing, do not trigger a new update, just write state
        self.async_write_ha_state()

    def toggle_paused(self):
        self._paused = not self._paused
        self.async_write_ha_state()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self) -> None:
        """Get the next journey."""
        if self._paused:
            _LOGGER.debug(f"Update paused for {self._name} due to internal pause attribute.")
            # Do not update state or attributes if paused
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


class VasttrafikJourneyListSensor(SensorEntity):
    """Sensor that lists all journeys for a route in a time window."""
    _attr_icon = "mdi:bus-clock"
    _attr_attribution = "Data provided by Västtrafik"

    def __init__(self, planner, name, origin, destination, lines, start_time, end_time, time_relates_to, index=None):
        self._planner = planner
        self._name = name or f"Journeys {origin} to {destination}"
        self._origin = origin
        self._destination = destination
        self._lines = lines if lines else None
        self._start_time = start_time
        self._end_time = end_time
        self._time_relates_to = time_relates_to
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"journeylist_{origin}_{destination}_{start_time}_{end_time}_{time_relates_to}_{index}"

    @property
    def name(self):
        return self._name

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def native_value(self):
        return self._state

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        # Get all journeys for the day in the specified window
        now_dt = now().replace(second=0, microsecond=0)
        today = now_dt.date()
        start_dt = datetime.combine(today, datetime.strptime(self._start_time, "%H:%M").time())
        end_dt = datetime.combine(today, datetime.strptime(self._end_time, "%H:%M").time())
        journeys = []
        dt = start_dt
        while dt <= end_dt:
            try:
                results = self._planner.trip(
                    origin_id=self._origin,
                    dest_id=self._destination,
                    date=dt,
                    dateTimeRelatesTo=self._time_relates_to,
                )
                for journey in results:
                    main_leg = next((l for l in journey.get("tripLegs", []) if l.get("serviceJourney")), None)
                    if not main_leg:
                        continue
                    line = main_leg.get("serviceJourney", {}).get("line", {})
                    if self._lines and line.get("shortName") not in self._lines:
                        continue
                    dep_time = main_leg.get("plannedDepartureTime")
                    arr_time = main_leg.get("plannedArrivalTime")
                    journeys.append({
                        "departure": dep_time,
                        "arrival": arr_time,
                        "line": line.get("shortName"),
                        "direction": main_leg.get("serviceJourney", {}).get("direction"),
                    })
            except Exception as ex:
                _LOGGER.warning(f"Failed to fetch journey at {dt}: {ex}")
            # Increment by 5 minutes (or as needed)
            dt += timedelta(minutes=5)
        self._attributes = {"journeys": journeys}
        self._state = len(journeys)