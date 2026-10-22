import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers import config_validation as cv
from .api import HeatitWiFi6API
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class HeatitWiFi6ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    
    VERSION = 1

    def __init__(self):
        self._host = None
        self._name = None

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            if "://" not in user_input[CONF_HOST]: 
                user_input[CONF_HOST] = "http://" + user_input[CONF_HOST]
            self._name = user_input[CONF_NAME]
            self._host = user_input[CONF_HOST]

            # Verify that a thermostat answers on the address before saving it.
            device_id = await HeatitWiFi6API(self._host).get_device_id(retries=1, timeout=8)
            if device_id == "unknown":
                _LOGGER.warning("Could not reach a Heatit thermostat at %s", self._host)
                errors["base"] = "cannot_connect"
            else:
                # The device id identifies the thermostat, so the same one cannot be added twice.
                await self.async_set_unique_id(str(device_id))
                self._abort_if_unique_id_configured()
                _LOGGER.info("add_device_done - name: %s, host: %s", str(self._name), str(self._host))
                return self.async_create_entry(
                    title = f"Heatit ({self._name})",
                    data = user_input
                )
        
        return self.async_show_form(
            step_id="user",
            data_schema = vol.Schema({
                vol.Required(CONF_NAME, default=(user_input or {}).get(CONF_NAME, vol.UNDEFINED)): cv.string,
                vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, vol.UNDEFINED)): cv.string
            }),
            errors = errors,
            description_placeholders = {
               CONF_NAME: "description_name",
               CONF_HOST: "description_host"
            }
        )
