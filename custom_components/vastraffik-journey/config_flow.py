import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_NAME
from .sensor import CONF_CLIENT_ID, CONF_SECRET, CONF_DEPARTURES, CONF_FROM, CONF_DESTINATION, CONF_DELAY, CONF_HEADING, CONF_LINES, DEFAULT_DELAY
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
        self._current_departure = None
        self._edit_index = None

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
            elif action == "finish":
                return self.async_create_entry(title="", data={CONF_DEPARTURES: self.departures})
        return self.async_show_form(
            step_id="menu",
            data_schema=menu_schema,
            errors=errors,
            description_placeholders={
                "departures": str(self.departures)
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
        choices = {str(i): f"{d.get(CONF_FROM)} → {d.get(CONF_DESTINATION)}" for i, d in enumerate(self.departures)}
        schema = vol.Schema({vol.Required("edit_index"): vol.In(list(choices.keys()))})
        if user_input is not None:
            idx = int(user_input["edit_index"])
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
            vol.Optional(CONF_LINES, default=", ".join(dep.get(CONF_LINES, [])) if isinstance(dep.get(CONF_LINES, list)) else str(dep.get(CONF_LINES, ""))): str,  # Show as comma-separated string
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
        choices = {str(i): f"{d.get(CONF_FROM)} → {d.get(CONF_DESTINATION)}" for i, d in enumerate(self.departures)}
        schema = vol.Schema({vol.Required("remove_index"): vol.In(list(choices.keys()))})
        if user_input is not None:
            idx = int(user_input["remove_index"])
            self.departures.pop(idx)
            return await self.async_step_menu()
        return self.async_show_form(
            step_id="select_remove",
            data_schema=schema,
            errors=errors,
            description_placeholders={"choices": str(choices)}
        )
