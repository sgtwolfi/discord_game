"""Admin-only WebSocket diagnostics for the GHOST control panel."""

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .services import assistants


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/assistant/diagnostics"}
)
@websocket_api.async_response
async def websocket_get_diagnostics(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
) -> None:
    """Return private assistant diagnostics to administrators only."""
    items = assistants(hass)
    if not items:
        connection.send_result(msg["id"], {"available": False})
        return

    connection.send_result(
        msg["id"],
        {"available": True, "diagnostics": items[0].diagnostics()},
    )




@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/assistant/conversation",
        vol.Required("conversation"): str,
    }
)
@websocket_api.async_response
async def websocket_get_conversation(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
) -> None:
    """Return messages for one approved DM or configured group channel."""
    items = assistants(hass)
    if not items:
        connection.send_result(msg["id"], {"available": False})
        return
    try:
        result = items[0].conversation_messages(msg["conversation"])
    except ValueError as err:
        connection.send_result(msg["id"], {"available": False, "error": str(err)})
        return
    connection.send_result(msg["id"], {"available": True, **result})


def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the diagnostics command once for this Home Assistant instance."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_ghost_ws_registered"):
        return
    websocket_api.async_register_command(hass, websocket_get_diagnostics)
    websocket_api.async_register_command(hass, websocket_get_conversation)
    data["_ghost_ws_registered"] = True
