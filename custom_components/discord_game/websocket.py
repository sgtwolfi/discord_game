"""Admin-only WebSocket diagnostics for the GHOST control panel."""

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.homeassistant.const import DATA_EXPOSED_ENTITIES
from homeassistant.components.homeassistant.exposed_entities import (
    async_expose_entity,
    async_should_expose,
)
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/assistant/capabilities"}
)
@websocket_api.async_response
async def websocket_get_capabilities(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
) -> None:
    """List Home Assistant entities and whether Assist can use them."""
    if DATA_EXPOSED_ENTITIES not in hass.data:
        connection.send_result(
            msg["id"],
            {"available": False, "error": "Home Assistant Assist exposure registry is unavailable."},
        )
        return
    registry = er.async_get(hass)
    entities = []
    for state in hass.states.async_all():
        entity_id = state.entity_id
        entry = registry.async_get(entity_id)
        attributes = state.attributes
        name = (
            attributes.get("friendly_name")
            or (entry.name if entry else None)
            or entity_id
        )
        entities.append({
            "entity_id": entity_id,
            "name": str(name),
            "domain": entity_id.split(".", 1)[0],
            "state": state.state,
            "exposed": async_should_expose(hass, "conversation", entity_id),
        })
    entities.sort(key=lambda item: (item["domain"] != "script", item["domain"], item["name"].casefold()))
    connection.send_result(
        msg["id"],
        {
            "available": True,
            "assistant": "conversation",
            "entities": entities,
            "script_count": sum(item["domain"] == "script" for item in entities),
            "exposed_count": sum(item["exposed"] for item in entities),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/assistant/capability/set",
        vol.Required("entity_id"): str,
        vol.Required("exposed"): bool,
    }
)
@websocket_api.async_response
async def websocket_set_capability(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict
) -> None:
    """Expose or unexpose one entity to Home Assistant Assist."""
    entity_id = msg["entity_id"]
    if hass.states.get(entity_id) is None:
        connection.send_error(msg["id"], "not_found", f"Entity {entity_id} does not exist")
        return
    if DATA_EXPOSED_ENTITIES not in hass.data:
        connection.send_error(msg["id"], "not_found", "Home Assistant Assist exposure registry is unavailable")
        return
    async_expose_entity(hass, "conversation", entity_id, msg["exposed"])
    connection.send_result(
        msg["id"],
        {"entity_id": entity_id, "exposed": msg["exposed"]},
    )


def async_register_websocket(hass: HomeAssistant) -> None:
    """Register the diagnostics command once for this Home Assistant instance."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("_ghost_ws_registered"):
        return
    websocket_api.async_register_command(hass, websocket_get_diagnostics)
    websocket_api.async_register_command(hass, websocket_get_conversation)
    websocket_api.async_register_command(hass, websocket_get_capabilities)
    websocket_api.async_register_command(hass, websocket_set_capability)
    data["_ghost_ws_registered"] = True
