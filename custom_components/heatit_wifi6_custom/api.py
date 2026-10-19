import aiohttp
import logging
import json
import asyncio
from .const import API_STATUS, API_PARAMETERS, API_RESET

_LOGGER = logging.getLogger(__name__)

# should an other side certificate verified when https used. (True/False)
# if certificate not verified, https works also with self signed certs.
TLS_CHECK = True

class HeatitWiFi6API:
    def __init__(self, host):
        self.__host = host.rstrip("/")

    async def _get(self, endpoint, timeout=5, retries=0):  # simple general http-get with optional retries
        url = f"{self.__host}{endpoint}"
        _LOGGER.debug("aiohttp - Get url: %s", url)

        for attempt in range(retries + 1):
            try:
                async with aiohttp.TCPConnector(ssl=TLS_CHECK, resolver=aiohttp.resolver.ThreadedResolver()) as conn:
                    async with aiohttp.ClientSession(connector=conn, trust_env=False) as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                            text = await response.text()
                            _LOGGER.debug(f"Response (get %s) data:\n%s", url, str(text))
                            return await self._parse_json(text)
            except asyncio.TimeoutError:
                if attempt < retries:
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s...
                    _LOGGER.debug("GET %s timed out (attempt %d/%d). Retrying in %d seconds...", url, attempt + 1, retries + 1, wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.debug("GET %s failed after %d attempts: Timeout (device may be slow to respond)", url, retries + 1)
                    return {}
            except Exception as e:
                if attempt < retries:
                    wait_time = (attempt + 1) * 2
                    _LOGGER.debug("GET %s failed (attempt %d/%d): %s. Retrying in %d seconds...", url, attempt + 1, retries + 1, str(e), wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.debug("GET %s failed after %d attempts: %s (device may be slow to respond)", url, retries + 1, str(e))
                    return {}
        return {}


    async def _post(self, endpoint, data, timeout=15, retries=2):  # simple general http-post with retries
        url = f"{self.__host}{endpoint}"
        _LOGGER.debug("aiohttp - Post url: %s", url)

        for attempt in range(retries + 1):
            try:
                async with aiohttp.TCPConnector(ssl=TLS_CHECK, resolver=aiohttp.resolver.ThreadedResolver()) as conn:
                    async with aiohttp.ClientSession(connector=conn, trust_env=False) as session:
                        async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                            text = await response.text()
                            _LOGGER.debug("Response (post %s) data:\n%s", url, str(text))
                            return await self._parse_json(text)
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                if attempt < retries:
                    wait_time = (attempt + 1) * 2
                    _LOGGER.warning(
                        "POST %s failed (attempt %d/%d), retrying in %ds... Error: %s",
                        url, attempt + 1, retries + 1, wait_time, str(e)
                    )
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.error(
                        "POST %s failed after %d attempts. Error: %s",
                        url, retries + 1, str(e)
                    )
                    return {}
            except Exception as e:
                if attempt < retries:
                    wait_time = (attempt + 1) * 2
                    _LOGGER.warning(
                        "POST %s failed (attempt %d/%d): %s. Retrying in %ds...",
                        url, attempt + 1, retries + 1, str(e), wait_time
                    )
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.error(
                        "POST %s failed after %d attempts: %s",
                        url, retries + 1, str(e)
                    )
                    return {}
        return {}


    async def _delete(self, endpoint, timeout=5):  # simple general http-delete
        url = f"{self.__host}{endpoint}"
        _LOGGER.debug("aiohttp - Delete url: %s", url)

        try:
            async with aiohttp.TCPConnector(ssl=TLS_CHECK, resolver=aiohttp.resolver.ThreadedResolver()) as conn:
                async with aiohttp.ClientSession(connector=conn, trust_env=False) as session:
                    async with session.delete(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                        text = await response.text()
                        _LOGGER.debug(f"Response (delete %s) data:\n%s", url, str(text))
                        return await self._parse_json(text)
        except Exception as e:
            _LOGGER.error("DELETE %s failed: %s", url, str(e))
            return {}


    # aiohttp response.json() require a correct content-type header on the http response.
    # parse json from response.text() is immune of content-type header.
    async def _parse_json(self, text):
       if not isinstance(text, str): return {}  # non string?
       text = text.strip()
       if not bool(text) or not text.startswith("{") or not text.endswith("}"): return {}  # not empty string and look like a json string?
       try:
           data = json.loads(text)
       except json.JSONDecodeError as e:
           data = {}
           _LOGGER.error("Json parsing failed. %s ", str(e))
       return data


    async def get_device_id(self, retries=0, timeout=8) -> str:
        """Get device ID with retry logic for slow WiFi connections during startup."""
        _LOGGER.debug("get_device_id() - Fetch device_id from the API (timeout=%ds, retries=%d)..", timeout, retries)
        data = await self._get(API_STATUS.rstrip("/"), timeout=timeout, retries=retries)
        device_id = data.get("id", "unknown")
        if device_id == "unknown":
            _LOGGER.debug("get_device_id() - Could not retrieve device ID (device may be slow to respond, will retry via polling)")
        return device_id


    async def get_status(self, retries=1, timeout=5) -> dict:
        """Get status with optional retry logic. Default: 1 retry with 5s timeout for normal polling."""
        _LOGGER.debug("get_status() - Fetch full status from the API (timeout=%ds, retries=%d)..", timeout, retries)
        return await self._get(API_STATUS.rstrip("/"), timeout=timeout, retries=retries)


    async def set_parameter(self, parameter, value) -> dict:
        _LOGGER.info("set_parameter(%s, %s) - Set parameter to the thermostat..", parameter, value)

        data = {parameter: value}
        response = await self._post(API_PARAMETERS.rstrip("/"), data, timeout=20, retries=3)

        if response and response.get("status", "Failed") == "Success":
            _LOGGER.debug("set_parameter(%s, %s): %s", parameter, value, response.get("value", "Success, but no value in response"))
            return response
        
        _LOGGER.error("set_parameter(%s, %s) failed: %s", parameter, value, str(response))
        return {}


    async def reset_device(self, reset_type="kwh") -> dict:
        _LOGGER.info("reset_device() - Resetting the Heatit thermostat. Reset type: %s", reset_type)

        if reset_type not in ["factory", "settings", "kwh"]:
            _LOGGER.error("Unknown reset_type: %s", reset_type)
            return { "status": "Failed", "detail": "Unknown reset_type." }
        
        response = await self._delete(f"{API_RESET.rstrip('/')}/{reset_type}")

        if response and response.get("status", "Failed") == "Success":
            _LOGGER.info("reset_device(%s): %s", reset_type, response.get("value", "Success, but no value in response"))
            return response
        
        _LOGGER.error("reset_device(%s) failed: %s", reset_type, str(response))
        return {}
