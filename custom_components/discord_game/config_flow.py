import logging
from typing import Optional, Dict, Any

import homeassistant.helpers.config_validation as cv
import nextcord
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers import selector
from nextcord import LoginFailure

from .const import DOMAIN, CONF_MEMBERS, CONF_CHANNELS, CONF_VOICE_CHANNELS, CONF_IMAGE_FORMAT, CONF_STEAM_API_KEY, CONF_ENTITIES_DISABLED_DEFAULT

_LOGGER = logging.getLogger(__name__)

AUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): cv.string,
        vol.Required(CONF_IMAGE_FORMAT, default='webp'): selector.SelectSelector(
            selector.SelectSelectorConfig(options=['png', 'webp', 'jpeg', 'jpg'],
                                          multiple=False,
                                          mode=selector.SelectSelectorMode.DROPDOWN),
        ),
        vol.Optional(CONF_STEAM_API_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
        ),
        vol.Required(CONF_ENTITIES_DISABLED_DEFAULT, default=False): selector.BooleanSelector(),
    }
)


async def _validate_auth_and_fetch_data(token: str):
    """Authenticate with Discord and fetch guild members and channels.

    Returns (members_dict, user_names, channels_dict, channel_names).
    Raises ValueError on auth failure.
    """
    client = nextcord.Client(intents=nextcord.Intents.all())
    try:
        await client.login(token)
        guilds_iter = client.fetch_guilds()
        _LOGGER.debug("fetch_guilds() type: %s, value: %r", type(guilds_iter), guilds_iter)
        guilds = [g async for g in guilds_iter]
        _LOGGER.debug("guilds (as list): %s", guilds)

        members = {}
        channels = {}
        voice_channels = {}

        for guild in guilds:
            _members_iter = guild.fetch_members()
            _LOGGER.debug("fetch_members() type: %s, value: %r", type(_members_iter), _members_iter)
            _members = [m async for m in _members_iter]
            _LOGGER.debug("members (as list): %s", _members)
            for member in _members:
                members[member.name] = member

            _channels = await guild.fetch_channels()
            for channel in _channels:
                if isinstance(channel, nextcord.VoiceChannel):
                    voice_channels[channel.name] = channel
                else:
                    channels[channel.name] = channel
        _LOGGER.debug("members: %s", members)
        _LOGGER.debug("channels: %s", channels)
        _LOGGER.debug("voice_channels: %s", voice_channels)

        user_names = list(members.keys())
        _LOGGER.debug("userNames: %s", user_names)

        channel_names = list(channels.keys())
        _LOGGER.debug("channelNames: %s", channel_names)

        voice_channel_names = list(voice_channels.keys())
        _LOGGER.debug("voiceChannelNames: %s", voice_channel_names)

        return members, user_names, channels, channel_names, voice_channels, voice_channel_names
    except LoginFailure:
        raise ValueError("Invalid access token")
    finally:
        await client.close()


class DiscordGameConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    data: Optional[Dict[str, Any]]

    def __init__(self):
        self.members = {}
        self.user_names = []
        self.channels = {}
        self.channel_names = []
        self.voice_channels = {}
        self.voice_channel_names = []

    @staticmethod
    def async_get_options_flow(_config_entry):
        return DiscordGameOptionsFlow()

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        if user_input is not None:
            if user_input.get("assistant_enabled") and not str(user_input.get("conversation_agent", "")).strip():
                errors["base"] = "assistant_agent_required"
            if not errors:
                try:
                    self.members, self.user_names, self.channels, self.channel_names, \
                        self.voice_channels, self.voice_channel_names = \
                        await _validate_auth_and_fetch_data(user_input[CONF_ACCESS_TOKEN])
                except ValueError:
                    errors["base"] = "auth"
            if not errors:
                self.data = user_input
                self.data[CONF_MEMBERS] = []
                self.data[CONF_CHANNELS] = []
                self.data[CONF_VOICE_CHANNELS] = []

                return await self.async_step_members()

        return self.async_show_form(
            step_id="user", data_schema=AUTH_SCHEMA, errors=errors
        )

    async def async_step_members(self, user_input: Optional[Dict[str, Any]] = None):
        _MEMBERS_SCHEMA = vol.Schema(
            {
                vol.Optional(CONF_MEMBERS): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=self.user_names,
                                                  multiple=True,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Optional(CONF_CHANNELS): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=self.channel_names,
                                                  multiple=True,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Optional(CONF_VOICE_CHANNELS): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=self.voice_channel_names,
                                                  multiple=True,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
            }
        )

        errors: Dict[str, str] = {}
        if user_input is not None:
            for user in user_input.get(CONF_MEMBERS, []):
                self.data[CONF_MEMBERS].append(self.members.get(user).id)
            if user_input.get(CONF_CHANNELS):
                for channel in user_input.get(CONF_CHANNELS):
                    self.data[CONF_CHANNELS].append(self.channels.get(channel).id)
            if user_input.get(CONF_VOICE_CHANNELS):
                for channel in user_input.get(CONF_VOICE_CHANNELS):
                    self.data[CONF_VOICE_CHANNELS].append(self.voice_channels.get(channel).id)

            return self.async_create_entry(title="Discord Game", data=self.data)

        return self.async_show_form(
            step_id="members", data_schema=_MEMBERS_SCHEMA, errors=errors
        )


class DiscordGameOptionsFlow(config_entries.OptionsFlow):
    def _get_current(self, key, default=None):
        """Get current value from options, falling back to data."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default if default is not None else "")
        )

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        errors: Dict[str, str] = {}
        current_token = self._get_current(CONF_ACCESS_TOKEN)
        if user_input is not None:
            self.options_data = dict(user_input)
            # The old 60-message setting was a compression threshold. It is
            # now raw retention, so migrate its untouched default to 8.
            legacy_memory_settings = "memory_batch_messages" not in self.config_entry.options
            legacy_history_limit = self._get_current("history_limit", 8)
            # Keep advanced panel settings when saving the integration's model selectors.
            advanced_defaults = {
                "assistant_mode": self._get_current("assistant_mode", "local"),
                "api_fallback_agent": self._get_current("api_fallback_agent", ""),
                "group_relevance_agent": self._get_current("group_relevance_agent", ""),
                "group_require_mention": self._get_current("group_require_mention", False),
                "group_participation_mode": self._get_current("group_participation_mode", "participant"),
                "group_continuity_seconds": self._get_current("group_continuity_seconds", 300),
                "spam_local_agent": self._get_current("spam_local_agent", ""),
                "spam_policy": self._get_current("spam_policy", "defer_local"),
                "spam_message_limit": self._get_current("spam_message_limit", 8),
                "spam_window_seconds": self._get_current("spam_window_seconds", 30),
                "spam_defer_minutes": self._get_current("spam_defer_minutes", 10),
                "spam_timeout_minutes": self._get_current("spam_timeout_minutes", 5),
                "local_reminder_script": self._get_current("local_reminder_script", "script.set_timer_alarm_or_reminder"),
                "ghost_status_entity": self._get_current("ghost_status_entity", "input_text.ghost_status"),
                "owner_name": self._get_current("owner_name", "Harvey"),
                "fallback_after_failures": 1,
                "queue_debounce_seconds": 2.5,
                "max_context_messages": 12,
                "context_budget_chars": 10000,
                "history_limit": 8,
                "memory_idle_seconds": 300,
                "memory_batch_messages": 20,
                "conversation_history_limit": 500,
                "typing_enabled": True,
                "assistant_group_channels": "",
                "conversation_system_prompt": "",
                "operations_system_prompt": "",
                "advanced_system_prompt": "",
                "assistant_approved_users": self._get_current("assistant_approved_users", self._get_current(CONF_MEMBERS, [])),
                "assistant_contact_names": self._get_current("assistant_contact_names", {}),
            }
            for key, default in advanced_defaults.items():
                self.options_data.setdefault(key, self._get_current(key, default))
            if legacy_memory_settings and int(legacy_history_limit or 0) == 60:
                self.options_data["history_limit"] = 8
            if self.options_data.get("assistant_enabled") and not str(self.options_data.get("conversation_agent", "")).strip():
                errors["base"] = "assistant_agent_required"
            # Saving assistant settings must not trigger a needless Discord API
            # login/member scan. That scan can fail on privileged intents or
            # transient Discord API errors and used to surface as HA "Unknown error".
            if not errors and str(user_input.get(CONF_ACCESS_TOKEN, "")).strip() == str(current_token).strip():
                self.options_data[CONF_MEMBERS] = list(self._get_current(CONF_MEMBERS, []))
                self.options_data[CONF_CHANNELS] = list(self._get_current(CONF_CHANNELS, []))
                self.options_data[CONF_VOICE_CHANNELS] = list(self._get_current(CONF_VOICE_CHANNELS, []))
                return self.async_create_entry(title="", data=self.options_data)

            if not errors:
                try:
                    self.members, self.user_names, self.channels, self.channel_names, \
                        self.voice_channels, self.voice_channel_names = \
                        await _validate_auth_and_fetch_data(user_input[CONF_ACCESS_TOKEN])
                except Exception as err:  # noqa: BLE001 - surface Discord/API failures in the form
                    _LOGGER.exception("Unable to validate updated Discord token or load server choices")
                    errors["base"] = "auth" if isinstance(err, ValueError) else "discord_api"

            if not errors:
                self.options_data[CONF_MEMBERS] = []
                self.options_data[CONF_CHANNELS] = []
                self.options_data[CONF_VOICE_CHANNELS] = []
                return await self.async_step_members()

        current_image_format = self._get_current(CONF_IMAGE_FORMAT, "webp")
        current_steam_key = self._get_current(CONF_STEAM_API_KEY)
        current_entities_disabled = self._get_current(CONF_ENTITIES_DISABLED_DEFAULT, False)
        options_schema = vol.Schema(
            {
                vol.Required(CONF_ACCESS_TOKEN, default=current_token): cv.string,
                vol.Required(CONF_IMAGE_FORMAT, default=current_image_format): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=['png', 'webp', 'jpeg', 'jpg'],
                                                  multiple=False,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Optional(CONF_STEAM_API_KEY, default=current_steam_key): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD),
                ),
                vol.Required(CONF_ENTITIES_DISABLED_DEFAULT, default=current_entities_disabled): selector.BooleanSelector(),
                vol.Required("assistant_enabled", default=self._get_current("assistant_enabled", False)): selector.BooleanSelector(),
                vol.Required("assistant_mode", default=self._get_current("assistant_mode", "local")): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=["local", "api"], multiple=False, mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Optional("conversation_agent", default=self._get_current("conversation_agent", "")): selector.ConversationAgentSelector(),
                vol.Optional("operations_agent", default=self._get_current("operations_agent", "")): selector.ConversationAgentSelector(),
                vol.Optional("fallback_agent", default=self._get_current("fallback_agent", "")): selector.ConversationAgentSelector(),
                vol.Optional("api_fallback_agent", default=self._get_current("api_fallback_agent", "")): selector.ConversationAgentSelector(),
                vol.Optional("group_relevance_agent", default=self._get_current("group_relevance_agent", "")): selector.ConversationAgentSelector(),
                vol.Required("group_participation_mode", default=self._get_current("group_participation_mode", "participant")): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[
                        {"label": "Participant (AI judges relevance like a group member)", "value": "participant"},
                        {"label": "Mention required", "value": "mention"},
                        {"label": "Always respond", "value": "always"},
                    ], multiple=False, mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Required("group_continuity_seconds", default=self._get_current("group_continuity_seconds", 300)): vol.All(vol.Coerce(int), vol.Range(min=0, max=1800)),
                vol.Optional("spam_local_agent", default=self._get_current("spam_local_agent", "")): selector.ConversationAgentSelector(),
                vol.Required("spam_policy", default=self._get_current("spam_policy", "defer_local")): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[{"label": "Defer to local model", "value": "defer_local"}, {"label": "Discord timeout", "value": "timeout"}, {"label": "Ignore during cooldown", "value": "ignore"}], multiple=False, mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Required("spam_message_limit", default=self._get_current("spam_message_limit", 8)): vol.All(vol.Coerce(int), vol.Range(min=3, max=30)),
                vol.Required("spam_window_seconds", default=self._get_current("spam_window_seconds", 30)): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Required("spam_defer_minutes", default=self._get_current("spam_defer_minutes", 10)): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                vol.Required("spam_timeout_minutes", default=self._get_current("spam_timeout_minutes", 5)): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=options_schema, errors=errors)

    async def async_step_members(self, user_input: Optional[Dict[str, Any]] = None):
        # Build a reverse lookup: ID -> name for pre-selecting current members/channels
        current_member_ids = set(self._get_current(CONF_MEMBERS, []))
        current_channel_ids = set(self._get_current(CONF_CHANNELS, []))
        current_voice_channel_ids = set(self._get_current(CONF_VOICE_CHANNELS, []))

        preselected_members = [
            name for name, member in self.members.items()
            if member.id in current_member_ids
        ]
        preselected_channels = [
            name for name, channel in self.channels.items()
            if channel.id in current_channel_ids
        ]
        preselected_voice_channels = [
            name for name, channel in self.voice_channels.items()
            if channel.id in current_voice_channel_ids
        ]

        _MEMBERS_SCHEMA = vol.Schema(
            {
                vol.Optional(CONF_MEMBERS, default=preselected_members): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=self.user_names,
                                                  multiple=True,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Optional(CONF_CHANNELS, default=preselected_channels): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=self.channel_names,
                                                  multiple=True,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
                vol.Optional(CONF_VOICE_CHANNELS, default=preselected_voice_channels): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=self.voice_channel_names,
                                                  multiple=True,
                                                  mode=selector.SelectSelectorMode.DROPDOWN),
                ),
            }
        )

        errors: Dict[str, str] = {}
        if user_input is not None:
            for user in user_input.get(CONF_MEMBERS, []):
                member = self.members.get(user)
                if member:
                    self.options_data[CONF_MEMBERS].append(member.id)
            for channel in user_input.get(CONF_CHANNELS, []):
                ch = self.channels.get(channel)
                if ch:
                    self.options_data[CONF_CHANNELS].append(ch.id)
            for channel in user_input.get(CONF_VOICE_CHANNELS, []):
                ch = self.voice_channels.get(channel)
                if ch:
                    self.options_data[CONF_VOICE_CHANNELS].append(ch.id)

            return self.async_create_entry(title="", data=self.options_data)

        return self.async_show_form(
            step_id="members", data_schema=_MEMBERS_SCHEMA, errors=errors
        )
