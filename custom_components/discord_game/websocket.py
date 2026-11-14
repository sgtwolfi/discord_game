"""Admin-only WebSocket diagnostics for the GHOST control panel."""

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .services import assistants


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/assistant/diagnostics"}
)
@websocket_api.async_response
async def websocket_get_diagnostics(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Return private assistant diagnostics to administrators only."""
    if not connection.user.is_admin:
        connection.send_error(
            msg["id"], "unauthorized", "Administrator access is required"
        )
        return

    items = assistants(hass)
    if not items:
        connection.send_result(msg["id"], {"available": False})
        return

    connection.send_result(
        msg["id"],
        {"available": True, "diagnostics": items[0].diagnostics()},
    )


def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the diagnostics command once for this Home Assistant instance."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_ghost_ws_registered"):
        return
    websocket_api.async_register_command(hass, websocket_get_diagnostics)
    data["_ghost_ws_registered"] = True
