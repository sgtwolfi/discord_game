"""Manual Home Assistant controls for the Discord assistant."""

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

SEND = vol.Schema({
    vol.Required("message"): cv.string,
    vol.Optional("user_id"): cv.string,
    vol.Optional("channel_id"): cv.string,
})
CLEAR = vol.Schema({vol.Required("user_id"): cv.string})
SET_MEMORY = vol.Schema({
    vol.Required("user_id"): cv.string,
    vol.Required("summary"): cv.string,
})
SET_CONTEXT = vol.Schema({
    vol.Required("conversation"): cv.string,
    vol.Required("context"): cv.string,
})
EDIT_QUEUE = vol.Schema({
    vol.Required("message_id"): cv.string,
    vol.Required("message"): cv.string,
})
CANCEL_QUEUE = vol.Schema({vol.Required("message_id"): cv.string})
REPLAY = vol.Schema({
    vol.Required("timestamp"): cv.string,
    vol.Required("conversation"): cv.string,
})
RESET_PROMPT = vol.Schema({
    vol.Required("prompt_key"): vol.In({
        "conversation_system_prompt",
        "operations_system_prompt",
        "advanced_system_prompt",
    }),
})

SETTINGS = vol.Schema({
    vol.Required("assistant_mode"): vol.In({"api", "local"}),
    vol.Required("fallback_after_failures"): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
    vol.Required("queue_debounce_seconds"): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=15)),
    vol.Required("max_context_messages"): vol.All(vol.Coerce(int), vol.Range(min=4, max=80)),
    vol.Required("context_budget_chars"): vol.All(vol.Coerce(int), vol.Range(min=2000, max=50000)),
    vol.Required("history_limit"): vol.All(vol.Coerce(int), vol.Range(min=0, max=200)),
    vol.Required("memory_idle_seconds"): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
    vol.Required("memory_batch_messages"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    vol.Required("conversation_history_limit"): vol.All(vol.Coerce(int), vol.Range(min=50, max=2000)),
    vol.Required("typing_enabled"): cv.boolean,
    vol.Required("assistant_group_channels"): cv.string,
    vol.Required("conversation_system_prompt"): vol.All(cv.string, vol.Length(max=6000)),
    vol.Required("operations_system_prompt"): vol.All(cv.string, vol.Length(max=6000)),
    vol.Required("advanced_system_prompt"): vol.All(cv.string, vol.Length(max=6000)),
})


def assistants(hass: HomeAssistant):
    """Return loaded assistant instances."""
    return [
        value["assistant"]
        for value in hass.data.get(DOMAIN, {}).values()
        if isinstance(value, dict) and value.get("assistant")
    ]


async def async_setup_services(hass: HomeAssistant):
    """Register assistant services once."""
    if hass.data.setdefault(DOMAIN, {}).get("_assistant_services"):
        return

    async def ensure_admin(call: ServiceCall):
        """Reject user-initiated control calls from non-admin accounts."""
        user_id = call.context.user_id
        if user_id is None:
            return
        user = await hass.auth.async_get_user(user_id)
        if user is None or not user.is_admin:
            raise HomeAssistantError("Administrator access is required for GHOST controls")

    async def send(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].send_manual(
            message=call.data["message"],
            user_id=call.data.get("user_id"),
            channel_id=call.data.get("channel_id"),
        )

    async def clear(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].clear_history(call.data["user_id"])

    async def set_context(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].set_context_note(
            call.data["conversation"], call.data["context"]
        )

    async def set_memory(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].set_friend_memory(
            call.data["user_id"], call.data["summary"]
        )

    async def replay(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].replay_transcript(
            call.data["timestamp"], call.data["conversation"]
        )

    async def pause(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].pause()

    async def resume(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].resume()

    async def edit_queue(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        if not await items[0].edit_queued_message(call.data["message_id"], call.data["message"]):
            raise HomeAssistantError("Queued message was not found")

    async def cancel_queued(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        if not await items[0].cancel_queued_message(call.data["message_id"]):
            raise HomeAssistantError("Queued message was not found")

    async def clear_queue(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].clear_queue()

    async def update_contacts(call: ServiceCall):
        await ensure_admin(call)
        items = assistants(hass)
        if not items:
            raise HomeAssistantError("Discord assistant is not loaded")
        await items[0].update_contacts(call.data["contacts"])

    async def update_settings(call: ServiceCall):
        """Persist advanced assistant settings and reload the integration."""
        await ensure_admin(call)
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("Discord Game config entry was not found")
        entry = entries[0]
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, **dict(call.data)},
        )

    async def reset_prompt(call: ServiceCall):
        """Remove a custom prompt override so the built-in default is used."""
        await ensure_admin(call)
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("Discord Game config entry was not found")
        entry = entries[0]
        key = call.data["prompt_key"]
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, key: ""},
        )

    hass.services.async_register(DOMAIN, "send_message", send, schema=SEND)
    hass.services.async_register(DOMAIN, "clear_friend_memory", clear, schema=CLEAR)
    hass.services.async_register(DOMAIN, "set_friend_memory", set_memory, schema=SET_MEMORY)
    hass.services.async_register(DOMAIN, "set_context_note", set_context, schema=SET_CONTEXT)
    hass.services.async_register(DOMAIN, "pause", pause)
    hass.services.async_register(DOMAIN, "resume", resume)
    hass.services.async_register(DOMAIN, "clear_queue", clear_queue)
    hass.services.async_register(DOMAIN, "edit_queued_message", edit_queue, schema=EDIT_QUEUE)
    hass.services.async_register(DOMAIN, "cancel_queued_message", cancel_queued, schema=CANCEL_QUEUE)
    hass.services.async_register(DOMAIN, "replay_transcript", replay, schema=REPLAY)
    hass.services.async_register(DOMAIN, "update_settings", update_settings, schema=SETTINGS)
    hass.services.async_register(DOMAIN, "reset_prompt", reset_prompt, schema=RESET_PROMPT)
    hass.services.async_register(DOMAIN, "update_contacts", update_contacts, schema=vol.Schema({vol.Required("contacts"): [vol.Schema({vol.Required("user_id"): cv.string, vol.Optional("name", default=""): cv.string})]}))
    hass.data[DOMAIN]["_assistant_services"] = True


async def async_unload_services(hass: HomeAssistant):
    """Remove services after the final integration entry unloads."""
    if assistants(hass):
        return
    for name in ("send_message", "clear_friend_memory", "set_friend_memory", "set_context_note", "pause", "resume", "clear_queue", "edit_queued_message", "cancel_queued_message", "replay_transcript", "update_settings", "reset_prompt", "update_contacts"):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
    hass.data.get(DOMAIN, {}).pop("_assistant_services", None)
