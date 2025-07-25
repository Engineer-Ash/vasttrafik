import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_NAME
from .sensor import CONF_CLIENT_ID, CONF_SECRET, CONF_DEPARTURES, CONF_FROM, CONF_DESTINATION, CONF_DELAY, CONF_HEADING, CONF_LINES, DEFAULT_DELAY, CONF_LIST_START_TIME, CONF_LIST_END_TIME, CONF_LIST_TIME_RELATES_TO
from vasttrafik import JournyPlanner
import logging

_LOGGER = logging.getLogger(__name__)
DOMAIN = "vastraffik_journey"

class VastraffikJourneyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vastraffik Journey."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Validate credentials before creating entry
            valid = await self._async_validate_credentials(user_input[CONF_CLIENT_ID], user_input[CONF_SECRET])
            if valid:
                await self.async_set_unique_id(user_input[CONF_CLIENT_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Västtrafik", data={
                    CONF_CLIENT_ID: user_input[CONF_CLIENT_ID],
                    CONF_SECRET: user_input[CONF_SECRET],
                })
            else:
                errors[CONF_CLIENT_ID] = "invalid_auth"

        schema = vol.Schema({
            vol.Required(CONF_CLIENT_ID): str,
            vol.Required(CONF_SECRET): str,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def _async_validate_credentials(self, client_id, secret):
        def validate():
            planner = JournyPlanner(client_id, secret)
            planner.location_name("Göteborg")
            return True
        try:
            return await self.hass.async_add_executor_job(validate)
        except Exception as ex:
            _LOGGER.warning("Västtrafik credential validation failed: %s", ex)
            return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return VastraffikJourneyOptionsFlowHandler(config_entry)

class VastraffikJourneyOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.departures = list(config_entry.options.get(CONF_DEPARTURES, []))
        self.journey_list_sensors = list(config_entry.options.get("journey_list_sensors", []))
        self._current_departure = None
        self._edit_index = None
        self._current_list_sensor = None
        self._edit_list_index = None

    def _get_credentials(self):
        # Prefer options, fallback to data
        client_id = self.config_entry.options.get(CONF_CLIENT_ID) or self.config_entry.data.get(CONF_CLIENT_ID)
        secret = self.config_entry.options.get(CONF_SECRET) or self.config_entry.data.get(CONF_SECRET)
        if not client_id or not secret:
            raise ValueError("Missing Västtrafik credentials in config entry.")
        return client_id, secret

    async def async_step_init(self, user_input=None):
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        errors = {}
        options = [
            ("add", "Add departure"),
            ("edit", "Edit departure"),
            ("remove", "Remove departure"),
            ("add_list", "Add journey list sensor"),
            ("edit_list", "Edit journey list sensor"),
            ("remove_list", "Remove journey list sensor"),
            ("finish", "Finish"),
        ]
        menu_schema = vol.Schema({
            vol.Required("action"): vol.In([x[0] for x in options]),
        })
        if user_input is not None:
            action = user_input["action"]
            if action == "add":
                return await self.async_step_add_departure()
            elif action == "edit":
                if not self.departures:
                    errors["base"] = "no_departures"
                else:
                    return await self.async_step_select_edit()
            elif action == "remove":
                if not self.departures:
                    errors["base"] = "no_departures"
                else:
                    return await self.async_step_select_remove()
            elif action == "add_list":
                return await self.async_step_add_list_sensor()
            elif action == "edit_list":
                if not self.journey_list_sensors:
                    errors["base"] = "no_list_sensors"
                else:
                    return await self.async_step_select_edit_list()
            elif action == "remove_list":
                if not self.journey_list_sensors:
                    errors["base"] = "no_list_sensors"
                else:
                    return await self.async_step_select_remove_list()
            elif action == "finish":
                return self.async_create_entry(title="", data={CONF_DEPARTURES: self.departures, "journey_list_sensors": self.journey_list_sensors})
        return self.async_show_form(
            step_id="menu",
            data_schema=menu_schema,
            errors=errors,
            description_placeholders={
                "departures": str(self.departures),
                "list_sensors": str(self.journey_list_sensors)
            }
        )

    async def async_step_add_departure(self, user_input=None):
        errors = {}
        if user_input is not None and "from_partial" in user_input:
            # Step 1: User entered a partial 'from' name, fetch suggestions
            partial = user_input["from_partial"]
            def get_suggestions():
                client_id, secret = self._get_credentials()
                planner = JournyPlanner(client_id, secret)
                return planner.location_name(partial)
            try:
                suggestions = await self.hass.async_add_executor_job(get_suggestions)
            except Exception as ex:
                _LOGGER.error("Failed to fetch location suggestions: %s", ex)
                errors["base"] = "location_error"
                suggestions = []
            choices = {str(i): loc["name"] for i, loc in enumerate(suggestions)}
            schema = vol.Schema({vol.Required("from_choice"): vol.In(list(choices.values()))})
            return self.async_show_form(
                step_id="add_departure_from_select",
                data_schema=schema,
                errors=errors,
                description_placeholders={"matches": ", ".join(choices.values())}
            )
        elif user_input is not None and "from_choice" in user_input:
            # Step 2: User selected a 'from' location, now prompt for destination
            self._current_departure = {CONF_FROM: user_input["from_choice"]}
            return await self.async_step_add_departure_destination()
        # Initial step: ask for partial 'from' name
        schema = vol.Schema({vol.Required("from_partial"): str})
        return self.async_show_form(
            step_id="add_departure",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_add_departure_from_select(self, user_input=None):
        """Handle the selection of a 'from' location from the dropdown."""
        if user_input is not None and "from_choice" in user_input:
            self._current_departure = {CONF_FROM: user_input["from_choice"]}
            return await self.async_step_add_departure_destination()
        # Defensive fallback: go back to add_departure if something goes wrong
        return await self.async_step_add_departure()

    async def async_step_add_departure_destination(self, user_input=None):
        errors = {}
        if user_input is not None and "destination_partial" in user_input:
            # Step 1: User entered a partial 'destination' name, fetch suggestions
            partial = user_input["destination_partial"]
            def get_suggestions():
                client_id, secret = self._get_credentials()
                planner = JournyPlanner(client_id, secret)
                return planner.location_name(partial)
            try:
                suggestions = await self.hass.async_add_executor_job(get_suggestions)
            except Exception as ex:
                _LOGGER.error("Failed to fetch location suggestions: %s", ex)
                errors["base"] = "location_error"
                suggestions = []
            choices = {str(i): loc["name"] for i, loc in enumerate(suggestions)}
            schema = vol.Schema({vol.Required("destination_choice"): vol.In(list(choices.values()))})
            return self.async_show_form(
                step_id="add_departure_destination_select",
                data_schema=schema,
                errors=errors,
                description_placeholders={"matches": ", ".join(choices.values())}
            )
        elif user_input is not None and "destination_choice" in user_input:
            # Step 2: User selected a 'destination' location, now prompt for the rest
            self._current_departure[CONF_DESTINATION] = user_input["destination_choice"]
            return await self.async_step_add_departure_details()
        # Initial step: ask for partial 'destination' name
        schema = vol.Schema({vol.Required("destination_partial"): str})
        return self.async_show_form(
            step_id="add_departure_destination",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_add_departure_destination_select(self, user_input=None):
        """Handle the selection of a 'destination' location from the dropdown."""
        if user_input is not None and "destination_choice" in user_input:
            self._current_departure[CONF_DESTINATION] = user_input["destination_choice"]
            return await self.async_step_add_departure_details()
        # Defensive fallback: go back to add_departure_destination if something goes wrong
        return await self.async_step_add_departure_destination()

    async def async_step_add_departure_details(self, user_input=None):
        errors = {}
        dep = self._current_departure or {}
        dep_schema = vol.Schema({
            vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): int,
            vol.Optional(CONF_HEADING): str,
            vol.Optional(CONF_LINES, default=""): str,
            vol.Optional(CONF_NAME): str,
        })
        if user_input is not None:
            dep.update(user_input)
            # Defensive: ensure CONF_LINES is always a list
            if isinstance(dep.get(CONF_LINES), list):
                dep[CONF_LINES] = [l.strip() for l in dep.get(CONF_LINES) if l.strip()]
            else:
                dep[CONF_LINES] = [l.strip() for l in dep.get(CONF_LINES, "").split(",") if l.strip()]
            self.departures.append(dep)
            self._current_departure = None
            return await self.async_step_menu()
        return self.async_show_form(
            step_id="add_departure_details",
            data_schema=dep_schema,
            errors=errors,
        )

    async def async_step_select_edit(self, user_input=None):
        errors = {}
        # Build friendly names for each departure
        choices = {}
        for i, d in enumerate(self.departures):
            if d.get(CONF_NAME):
                label = d[CONF_NAME]
            elif d.get(CONF_FROM) and d.get(CONF_DESTINATION):
                label = f"{d.get(CONF_FROM)} → {d.get(CONF_DESTINATION)}"
            else:
                label = f"Journey {i+1}"
            # Ensure unique label in case of duplicates
            while label in choices:
                label += f" ({i+1})"
            choices[label] = i
        schema = vol.Schema({vol.Required("edit_label"): vol.In(list(choices.keys()))})
        if user_input is not None:
            idx = choices[user_input["edit_label"]]
            self._edit_index = idx
            self._current_departure = self.departures[idx]
            return await self.async_step_edit_departure()
        return self.async_show_form(
            step_id="select_edit",
            data_schema=schema,
            errors=errors,
            description_placeholders={"choices": str(choices)}
        )

    async def async_step_edit_departure(self, user_input=None):
        errors = {}
        dep = self._current_departure or {}
        dep_schema = vol.Schema({
            vol.Required(CONF_FROM, default=dep.get(CONF_FROM, "")): str,
            vol.Required(CONF_DESTINATION, default=dep.get(CONF_DESTINATION, "")): str,
            vol.Optional(CONF_DELAY, default=dep.get(CONF_DELAY, DEFAULT_DELAY)): int,
            vol.Optional(CONF_HEADING, default=dep.get(CONF_HEADING, "")): str,
            vol.Optional(CONF_LINES, default=", ".join(dep.get(CONF_LINES, [])) if isinstance(dep.get(CONF_LINES), list) else str(dep.get(CONF_LINES, ""))): str,  # Show as comma-separated string
            vol.Optional(CONF_NAME, default=dep.get(CONF_NAME, "")): str,
        })
        if user_input is not None:
            dep = dict(user_input)
            # Defensive: ensure CONF_LINES is always a list
            if isinstance(dep.get(CONF_LINES), list):
                dep[CONF_LINES] = [l.strip() for l in dep.get(CONF_LINES) if l.strip()]
            else:
                dep[CONF_LINES] = [l.strip() for l in dep.get(CONF_LINES, "").split(",") if l.strip()]
            self.departures[self._edit_index] = dep
            self._current_departure = None
            self._edit_index = None
            return await self.async_step_menu()
        return self.async_show_form(
            step_id="edit_departure",
            data_schema=dep_schema,
            errors=errors,
        )

    async def async_step_select_remove(self, user_input=None):
        errors = {}
        # Build friendly names for each departure
        choices = {}
        for i, d in enumerate(self.departures):
            if d.get(CONF_NAME):
                label = d[CONF_NAME]
            elif d.get(CONF_FROM) and d.get(CONF_DESTINATION):
                label = f"{d.get(CONF_FROM)} → {d.get(CONF_DESTINATION)}"
            else:
                label = f"Journey {i+1}"
            # Ensure unique label in case of duplicates
            while label in choices:
                label += f" ({i+1})"
            choices[label] = i
        schema = vol.Schema({vol.Required("remove_label"): vol.In(list(choices.keys()))})
        if user_input is not None:
            idx = choices[user_input["remove_label"]]
            self.departures.pop(idx)
            return await self.async_step_menu()
        return self.async_show_form(
            step_id="select_remove",
            data_schema=schema,
            errors=errors,
            description_placeholders={"choices": str(choices)}
        )

    async def async_step_add_list_sensor(self, user_input=None):
        errors = {}
        if user_input is not None and "from_partial" in user_input:
            # Step 1: User entered a partial 'from' name, fetch suggestions
            partial = user_input["from_partial"]
            def get_suggestions():
                client_id, secret = self._get_credentials()
                planner = JournyPlanner(client_id, secret)
                return planner.location_name(partial)
            try:
                suggestions = await self.hass.async_add_executor_job(get_suggestions)
            except Exception as ex:
                _LOGGER.error("Failed to fetch location suggestions: %s", ex)
                errors["base"] = "location_error"
                suggestions = []
            choices = {str(i): loc["name"] for i, loc in enumerate(suggestions)}
            schema = vol.Schema({vol.Required("from_choice"): vol.In(list(choices.values()))})
            return self.async_show_form(
                step_id="add_list_sensor_from_select",
                data_schema=schema,
                errors=errors,
                description_placeholders={"matches": ", ".join(choices.values())}
            )
        elif user_input is not None and "from_choice" in user_input:
            # Step 2: User selected a 'from' location, now prompt for destination
            self._current_list_sensor = {CONF_FROM: user_input["from_choice"]}
            return await self.async_step_add_list_sensor_destination()
        # Initial step: ask for partial 'from' name
        schema = vol.Schema({vol.Required("from_partial"): str})
        return self.async_show_form(
            step_id="add_list_sensor",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_add_list_sensor_from_select(self, user_input=None):
        if user_input is not None and "from_choice" in user_input:
            self._current_list_sensor = {CONF_FROM: user_input["from_choice"]}
            return await self.async_step_add_list_sensor_destination()
        return await self.async_step_add_list_sensor()

    async def async_step_add_list_sensor_destination(self, user_input=None):
        errors = {}
        if user_input is not None and "destination_partial" in user_input:
            partial = user_input["destination_partial"]
            def get_suggestions():
                client_id, secret = self._get_credentials()
                planner = JournyPlanner(client_id, secret)
                return planner.location_name(partial)
            try:
                suggestions = await self.hass.async_add_executor_job(get_suggestions)
            except Exception as ex:
                _LOGGER.error("Failed to fetch location suggestions: %s", ex)
                errors["base"] = "location_error"
                suggestions = []
            choices = {str(i): loc["name"] for i, loc in enumerate(suggestions)}
            schema = vol.Schema({vol.Required("destination_choice"): vol.In(list(choices.values()))})
            return self.async_show_form(
                step_id="add_list_sensor_destination_select",
                data_schema=schema,
                errors=errors,
                description_placeholders={"matches": ", ".join(choices.values())}
            )
        elif user_input is not None and "destination_choice" in user_input:
            self._current_list_sensor[CONF_DESTINATION] = user_input["destination_choice"]
            return await self.async_step_add_list_sensor_details()
        schema = vol.Schema({vol.Required("destination_partial"): str})
        return self.async_show_form(
            step_id="add_list_sensor_destination",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_add_list_sensor_destination_select(self, user_input=None):
        if user_input is not None and "destination_choice" in user_input:
            self._current_list_sensor[CONF_DESTINATION] = user_input["destination_choice"]
            return await self.async_step_add_list_sensor_details()
        return await self.async_step_add_list_sensor_destination()

    async def async_step_add_list_sensor_details(self, user_input=None):
        errors = {}
        ls = self._current_list_sensor or {}
        schema = vol.Schema({
            vol.Optional(CONF_LINES, default=""): str,
            vol.Optional(CONF_NAME): str,
            vol.Required(CONF_LIST_START_TIME): str,
            vol.Required(CONF_LIST_END_TIME): str,
            vol.Optional(CONF_LIST_TIME_RELATES_TO, default="departure"): vol.In(["departure", "arrival"]),
        })
        if user_input is not None:
            import re
            from datetime import datetime
            import pytz
            def parse_time_to_rfc3339(timestr):
                match = re.match(r"^(\d{1,2})(?::(\d{2}))?$", timestr.strip())
                if not match:
                    return None
                hour = int(match.group(1))
                minute = int(match.group(2) or 0)
                tz = pytz.timezone("Europe/Stockholm")
                now_dt = datetime.now(tz)
                dt = tz.localize(datetime(now_dt.year, now_dt.month, now_dt.day, hour, minute))
                return dt.isoformat()
            lines = [l.strip() for l in user_input.get(CONF_LINES, "").split(",") if l.strip()]
            ls[CONF_LINES] = lines
            ls[CONF_NAME] = user_input.get(CONF_NAME, "")
            # Run blocking time parsing in executor
            start_rfc = await self.hass.async_add_executor_job(parse_time_to_rfc3339, user_input[CONF_LIST_START_TIME])
            end_rfc = await self.hass.async_add_executor_job(parse_time_to_rfc3339, user_input[CONF_LIST_END_TIME])
            if not start_rfc or not end_rfc:
                errors[CONF_LIST_START_TIME] = "invalid_time_format"
                errors[CONF_LIST_END_TIME] = "invalid_time_format"
            else:
                ls[CONF_LIST_START_TIME] = start_rfc
                ls[CONF_LIST_END_TIME] = end_rfc
                ls[CONF_LIST_TIME_RELATES_TO] = user_input.get(CONF_LIST_TIME_RELATES_TO, "departure")
                self.journey_list_sensors.append(ls)
                self._current_list_sensor = None
                return await self.async_step_menu()
        return self.async_show_form(
            step_id="add_list_sensor_details",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_select_edit_list(self, user_input=None):
        errors = {}
        # Build friendly names for each journey list sensor
        choices = {}
        for i, ls in enumerate(self.journey_list_sensors):
            if ls.get(CONF_NAME):
                label = ls[CONF_NAME]
            elif ls.get(CONF_FROM) and ls.get(CONF_DESTINATION):
                label = f"{ls.get(CONF_FROM)} → {ls.get(CONF_DESTINATION)}"
            else:
                label = f"List Sensor {i+1}"
            while label in choices:
                label += f" ({i+1})"
            choices[label] = i
        schema = vol.Schema({vol.Required("edit_list_label"): vol.In(list(choices.keys()))})
        if user_input is not None:
            idx = choices[user_input["edit_list_label"]]
            self._edit_list_index = idx
            self._current_list_sensor = self.journey_list_sensors[idx]
            return await self.async_step_edit_list_sensor()
        return self.async_show_form(
            step_id="select_edit_list",
            data_schema=schema,
            errors=errors,
            description_placeholders={"choices": str(choices)}
        )

    async def async_step_edit_list_sensor(self, user_input=None):
        errors = {}
        ls = self._current_list_sensor or {}
        schema = vol.Schema({
            vol.Required(CONF_FROM, default=ls.get(CONF_FROM, "")): str,
            vol.Required(CONF_DESTINATION, default=ls.get(CONF_DESTINATION, "")): str,
            vol.Optional(CONF_LINES, default=", ".join(ls.get(CONF_LINES, [])) if isinstance(ls.get(CONF_LINES), list) else str(ls.get(CONF_LINES, ""))): str,
            vol.Optional(CONF_NAME, default=ls.get(CONF_NAME, "")): str,
            vol.Required(CONF_LIST_START_TIME, default=ls.get(CONF_LIST_START_TIME, "")): str,
            vol.Required(CONF_LIST_END_TIME, default=ls.get(CONF_LIST_END_TIME, "")): str,
            vol.Optional(CONF_LIST_TIME_RELATES_TO, default=ls.get(CONF_LIST_TIME_RELATES_TO, "departure")): vol.In(["departure", "arrival"]),
        })
        if user_input is not None:
            import re
            from datetime import datetime
            import pytz
            def parse_time_to_rfc3339(timestr):
                match = re.match(r"^(\d{1,2})(?::(\d{2}))?$", timestr.strip())
                if not match:
                    return None
                hour = int(match.group(1))
                minute = int(match.group(2) or 0)
                tz = pytz.timezone("Europe/Stockholm")
                now_dt = datetime.now(tz)
                dt = tz.localize(datetime(now_dt.year, now_dt.month, now_dt.day, hour, minute))
                return dt.isoformat()
            lines = [l.strip() for l in user_input.get(CONF_LINES, "").split(",") if l.strip()]
            ls[CONF_FROM] = user_input[CONF_FROM]
            ls[CONF_DESTINATION] = user_input[CONF_DESTINATION]
            ls[CONF_LINES] = lines
            ls[CONF_NAME] = user_input.get(CONF_NAME, "")
            # Run blocking time parsing in executor
            start_rfc = await self.hass.async_add_executor_job(parse_time_to_rfc3339, user_input[CONF_LIST_START_TIME])
            end_rfc = await self.hass.async_add_executor_job(parse_time_to_rfc3339, user_input[CONF_LIST_END_TIME])
            if not start_rfc or not end_rfc:
                errors[CONF_LIST_START_TIME] = "invalid_time_format"
                errors[CONF_LIST_END_TIME] = "invalid_time_format"
            else:
                ls[CONF_LIST_START_TIME] = start_rfc
                ls[CONF_LIST_END_TIME] = end_rfc
                ls[CONF_LIST_TIME_RELATES_TO] = user_input.get(CONF_LIST_TIME_RELATES_TO, "departure")
                self.journey_list_sensors[self._edit_list_index] = ls
                self._current_list_sensor = None
                self._edit_list_index = None
                return await self.async_step_menu()
        return self.async_show_form(
            step_id="edit_list_sensor",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_select_remove_list(self, user_input=None):
        errors = {}
        # Build friendly names for each journey list sensor
        choices = {}
        for i, ls in enumerate(self.journey_list_sensors):
            if ls.get(CONF_NAME):
                label = ls[CONF_NAME]
            elif ls.get(CONF_FROM) and ls.get(CONF_DESTINATION):
                label = f"{ls.get(CONF_FROM)} → {ls.get(CONF_DESTINATION)}"
            else:
                label = f"List Sensor {i+1}"
            while label in choices:
                label += f" ({i+1})"
            choices[label] = i
        schema = vol.Schema({vol.Required("remove_list_label"): vol.In(list(choices.keys()))})
        if user_input is not None:
            idx = choices[user_input["remove_list_label"]]
            self.journey_list_sensors.pop(idx)
            return await self.async_step_menu()
        return self.async_show_form(
            step_id="select_remove_list",
            data_schema=schema,
            errors=errors,
            description_placeholders={"choices": str(choices)}
        )
