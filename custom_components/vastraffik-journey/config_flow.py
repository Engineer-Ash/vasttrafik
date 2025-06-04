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
        return VasttrafikOptionsFlowHandler(config_entry)

class VasttrafikOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self.departures = list(config_entry.options.get(CONF_DEPARTURES, []))

    async def async_step_init(self, user_input=None):
        return await self.async_step_departures()

    async def async_step_departures(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Validate departures list
            if not isinstance(user_input[CONF_DEPARTURES], list) or not user_input[CONF_DEPARTURES]:
                errors[CONF_DEPARTURES] = "empty_departures"
            else:
                return self.async_create_entry(title="", data={CONF_DEPARTURES: user_input[CONF_DEPARTURES]})

        departures_schema = vol.Schema({
            vol.Required(CONF_DEPARTURES, default=self.departures): vol.All(
                [
                    {
                        vol.Required(CONF_FROM): str,
                        vol.Required(CONF_DESTINATION): str,
                        vol.Optional(CONF_DELAY, default=DEFAULT_DELAY): int,
                        vol.Optional(CONF_HEADING): str,
                        vol.Optional(CONF_LINES, default=[]): [str],
                        vol.Optional(CONF_NAME): str,
                    }
                ]
            ),
        })
        return self.async_show_form(
            step_id="departures",
            data_schema=departures_schema,
            errors=errors,
        )
