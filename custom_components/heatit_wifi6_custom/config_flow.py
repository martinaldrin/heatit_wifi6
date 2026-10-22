import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from .api import HeatitWiFi6API
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _base_url(host, port):
    """Build the thermostat's base URL from a discovered address."""
    return f"http://{host}" if port in (None, 80) else f"http://{host}:{port}"


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

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo):
        """Handle a thermostat announcing itself on the network (WiFi7).

        The announcement carries the same id as /api/status. A thermostat that is
        already set up only gets its address updated, so it keeps working when the
        router hands out a new IP.
        """
        device_id = discovery_info.properties.get("id")
        if not device_id:
            return self.async_abort(reason="not_heatit_device")

        url = _base_url(discovery_info.host, discovery_info.port)
        await self.async_set_unique_id(str(device_id))

        # Announcements repeat; do nothing if the thermostat is already set up on this address.
        known = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, self.unique_id)
        if known is not None and known.data.get(CONF_HOST) == url:
            return self.async_abort(reason="already_configured")

        # Only act on an announcement if the device really answers like that thermostat there.
        status = await HeatitWiFi6API(url).get_status(retries=1, timeout=8)
        if not status or "parameters" not in status or str(status.get("id")) != str(device_id):
            _LOGGER.debug("Discovered %s did not answer as the Heatit thermostat %s", url, device_id)
            return self.async_abort(reason="cannot_connect")

        # Already set up under another address: follow it to the new one.
        self._abort_if_unique_id_configured(updates={CONF_HOST: url})

        self._host = url
        self._name = status.get("room") or status.get("name") or "Heatit"
        self.context["title_placeholders"] = {CONF_NAME: self._name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=f"Heatit ({user_input[CONF_NAME]})",
                data={CONF_NAME: user_input[CONF_NAME], CONF_HOST: self._host},
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default=self._name): cv.string}),
            description_placeholders={CONF_HOST: self._host},
        )
