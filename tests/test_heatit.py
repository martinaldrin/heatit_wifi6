"""Tests for the heatit_wifi6 integration, run against a real Home Assistant core and a
fake thermostat. The WiFi6 and WiFi7 status payloads in tests/fixtures are real device
responses with identifiers replaced."""
import json
from pathlib import Path

import pytest
from aiohttp import web
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

DOMAIN = "heatit_wifi6"
FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


async def _serve(payload):
    """Serve `payload` as /api/status; POSTs to /api/parameters update it."""
    state = {"payload": payload, "posts": []}

    async def status(request):
        return web.json_response(state["payload"])

    async def params(request):
        body = await request.json()
        state["posts"].append(body)
        state["payload"]["parameters"].update(body)
        return web.json_response({"status": "Success", "value": list(body.values())[0]})

    app = web.Application()
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/parameters", params)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    state["url"] = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    state["runner"] = runner
    return state


@pytest.fixture
async def wifi6(socket_enabled):
    state = await _serve(_load("wifi6_status.json"))
    yield state
    await state["runner"].cleanup()


@pytest.fixture
async def wifi7(socket_enabled):
    state = await _serve(_load("wifi7_status.json"))
    yield state
    await state["runner"].cleanup()


@pytest.fixture
async def thermostat(request, socket_enabled):
    """Use with @pytest.mark.parametrize("thermostat", [...], indirect=True)."""
    state = await _serve(_load(f"{request.param}_status.json"))
    yield state
    await state["runner"].cleanup()


async def _add(hass, url, name="Test"):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    return await hass.config_entries.flow.async_configure(r["flow_id"], {"name": name, "host": url})


async def _entity(hass, thermostat):
    r = await _add(hass, thermostat["url"])
    await hass.async_block_till_done()
    states = hass.states.async_all("climate")
    assert len(states) == 1, [s.entity_id for s in states]
    return r["result"], states[0]


# ---------------------------------------------------------------- config flow
async def test_flow_rejects_unreachable_host(hass, enable_custom_integrations, socket_enabled):
    r = await _add(hass, "127.0.0.1:9")
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize("thermostat, device_id", [("wifi6", "TESTWIFI6DEVICEID"), ("wifi7", "TESTWIFI7DEVICEID")], indirect=["thermostat"])
async def test_flow_creates_entry_with_device_id(hass, enable_custom_integrations, thermostat, device_id):
    r = await _add(hass, thermostat["url"])
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["result"].unique_id == device_id


async def test_flow_rejects_duplicate(hass, enable_custom_integrations, wifi7):
    assert (await _add(hass, wifi7["url"]))["type"] == FlowResultType.CREATE_ENTRY
    second = await _add(hass, wifi7["url"], name="Again")
    assert second["type"] == FlowResultType.ABORT
    assert second["reason"] == "already_configured"


# ------------------------------------------------------------- model support
async def test_wifi7_reads_new_fields(hass, enable_custom_integrations, wifi7):
    _, state = await _entity(hass, wifi7)
    a = state.attributes
    assert state.state == "heat"
    assert a["hw_model"] == "Heatit WiFi7"
    assert a["hw_firmware"] == "0.1.16"
    # WiFi7 renamed the calibration parameters to ...SensorCalibration.
    assert a["param_internalCalibration"] == 0.0
    assert a["param_floorCalibration"] == 0.0
    assert a["param_externalCalibration"] == 0.0
    assert a["info_totalConsumption"] is not None
    assert a["info_currentPower"] is not None


async def test_wifi6_still_reads_old_fields(hass, enable_custom_integrations, wifi6):
    _, state = await _entity(hass, wifi6)
    a = state.attributes
    assert a["hw_model"] == "Heatit WiFi6"  # the WiFi6 payload has no "model"
    assert a["hw_firmware"] == "2.26"
    assert a["param_internalCalibration"] is not None
    assert a["param_floorCalibration"] is not None


@pytest.mark.parametrize("thermostat, model, firmware", [("wifi6", "Heatit WiFi6", "2.26"), ("wifi7", "Heatit WiFi7", "0.1.16")], indirect=["thermostat"])
async def test_device_registry_entry(hass, enable_custom_integrations, thermostat, model, firmware):
    entry, _ = await _entity(hass, thermostat)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    assert devices[0].manufacturer == "Heatit"
    assert devices[0].model == model
    assert devices[0].sw_version == firmware


# ---------------------------------------------------------------- discovery
def _zeroconf_info(url, device_id, name="directlink._tf._tcp.local."):
    from ipaddress import ip_address
    from urllib.parse import urlparse
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
    u = urlparse(url)
    return ZeroconfServiceInfo(
        ip_address=ip_address(u.hostname), ip_addresses=[ip_address(u.hostname)],
        port=u.port, hostname="tf-test.local.", type="_tf._tcp.local.", name=name,
        properties={"id": device_id, "mid": device_id, "state": "stop"})


async def _discover(hass, info):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "zeroconf"}, data=info)


async def test_manifest_registers_the_mdns_service(hass, enable_custom_integrations):
    from homeassistant.loader import async_get_zeroconf
    matchers = (await async_get_zeroconf(hass)).get("_tf._tcp.local.", [])
    assert any(m["domain"] == DOMAIN and m.get("name") == "directlink*" for m in matchers), matchers


async def test_discovery_offers_a_new_thermostat(hass, enable_custom_integrations, wifi7):
    r = await _discover(hass, _zeroconf_info(wifi7["url"], "TESTWIFI7DEVICEID"))
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "discovery_confirm"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"name": "Hall"})
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["result"].unique_id == "TESTWIFI7DEVICEID"
    assert r["data"] == {"name": "Hall", "host": wifi7["url"]}


async def test_discovery_updates_the_address_of_a_known_thermostat(hass, enable_custom_integrations, wifi7):
    """The router gave the thermostat a new IP: the entry must follow it."""
    r = await _add(hass, wifi7["url"])
    entry = r["result"]
    entry_data_before = entry.data["host"]
    # Same thermostat now answers on another address (a second local server stands in for it).
    other = await _serve(_load("wifi7_status.json"))
    try:
        res = await _discover(hass, _zeroconf_info(other["url"], "TESTWIFI7DEVICEID"))
        await hass.async_block_till_done()
        assert res["type"] == FlowResultType.ABORT and res["reason"] == "already_configured"
        assert entry.data["host"] == other["url"] != entry_data_before
    finally:
        await other["runner"].cleanup()


async def test_discovery_does_not_move_a_thermostat_to_an_address_that_does_not_answer(
        hass, enable_custom_integrations, wifi7):
    r = await _add(hass, wifi7["url"])
    entry = r["result"]
    res = await _discover(hass, _zeroconf_info("http://127.0.0.1:9", "TESTWIFI7DEVICEID"))
    assert res["type"] == FlowResultType.ABORT and res["reason"] == "cannot_connect"
    assert entry.data["host"] == wifi7["url"]


async def test_discovery_does_not_move_a_thermostat_to_a_different_device(
        hass, enable_custom_integrations, wifi6, wifi7):
    """An announcement whose address answers with another id must be ignored."""
    entry = (await _add(hass, wifi7["url"]))["result"]
    res = await _discover(hass, _zeroconf_info(wifi6["url"], "TESTWIFI7DEVICEID"))
    assert res["type"] == FlowResultType.ABORT and res["reason"] == "cannot_connect"
    assert entry.data["host"] == wifi7["url"]


async def test_discovery_ignores_something_that_is_not_a_heatit(hass, enable_custom_integrations, socket_enabled):
    # Nothing answers like a thermostat on this port.
    res = await _discover(hass, _zeroconf_info("http://127.0.0.1:9", "SOMEID"))
    assert res["type"] == FlowResultType.ABORT and res["reason"] == "cannot_connect"


async def test_discovery_without_id_is_rejected(hass, enable_custom_integrations, wifi7):
    info = _zeroconf_info(wifi7["url"], "x")
    info.properties.pop("id")
    res = await _discover(hass, info)
    assert res["type"] == FlowResultType.ABORT and res["reason"] == "not_heatit_device"


async def test_old_entry_without_unique_id_gets_one(hass, enable_custom_integrations, wifi7):
    """Entries created before the id was stored must be recognisable by discovery."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(domain=DOMAIN, data={"name": "Old", "host": wifi7["url"]}, unique_id=None)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.unique_id == "TESTWIFI7DEVICEID"


# ---------------------------------------------------------------- control
@pytest.mark.parametrize("thermostat", ["wifi6", "wifi7"], indirect=True)
async def test_set_temperature_while_on(hass, enable_custom_integrations, thermostat):
    thermostat["payload"]["parameters"]["operatingMode"] = 1
    _, state = await _entity(hass, thermostat)
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": state.entity_id, "temperature": 23}, blocking=True)
    await hass.async_block_till_done()
    assert thermostat["payload"]["parameters"]["heatingSetpoint"] == 23
    assert hass.states.get(state.entity_id).attributes["temperature"] == 23


async def test_set_temperature_while_off_does_not_crash(hass, enable_custom_integrations, wifi6):
    assert await async_setup_component(hass, "persistent_notification", {})
    wifi6["payload"]["parameters"]["operatingMode"] = 0
    _, state = await _entity(hass, wifi6)
    assert state.state == "off"
    # Used to raise AttributeError: 'HomeAssistant' object has no attribute 'components'
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": state.entity_id, "temperature": 22}, blocking=True)
    assert wifi6["posts"] == [], "must not write a setpoint while the device is off"


async def test_unknown_operating_mode_does_not_block_later_updates(hass, enable_custom_integrations, wifi6):
    """An unknown mode used to leave _set_temperature_pending=True forever."""
    wifi6["payload"]["parameters"]["operatingMode"] = 9
    _, state = await _entity(hass, wifi6)
    ent = hass.data["entity_components"]["climate"].get_entity(state.entity_id)
    await ent.async_set_temperature(temperature=21)
    assert ent._set_temperature_pending is False
