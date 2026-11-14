"""Manual Home Assistant controls for the Discord assistant."""
import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN
SEND=vol.Schema({vol.Required("message"):cv.string,vol.Optional("user_id"):cv.string,vol.Optional("channel_id"):cv.string})
CLEAR=vol.Schema({vol.Required("user_id"):cv.string})
def assistants(hass):
    return [v["assistant"] for v in hass.data.get(DOMAIN,{}).values() if isinstance(v,dict) and v.get("assistant")]
async def async_setup_services(hass:HomeAssistant):
    if hass.data.setdefault(DOMAIN,{}).get("_assistant_services"):return
    async def send(call:ServiceCall):
        items=assistants(hass)
        if not items:raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].send_manual(message=call.data["message"],user_id=call.data.get("user_id"),channel_id=call.data.get("channel_id"))
    async def clear(call:ServiceCall):
        items=assistants(hass)
        if not items:raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].clear_history(call.data["user_id"])
    hass.services.async_register(DOMAIN,"send_message",send,schema=SEND)
    hass.services.async_register(DOMAIN,"clear_friend_memory",clear,schema=CLEAR)
    hass.data[DOMAIN]["_assistant_services"]=True
async def async_unload_services(hass:HomeAssistant):
    if assistants(hass):return
    for name in ("send_message","clear_friend_memory"):
        if hass.services.has_service(DOMAIN,name):hass.services.async_remove(DOMAIN,name)
    hass.data.get(DOMAIN,{}).pop("_assistant_services",None)
