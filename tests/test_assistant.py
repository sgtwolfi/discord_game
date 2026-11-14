"""Focused tests for GHOST context and response handling without a live HA instance."""

import asyncio
import importlib
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

# The tested helpers do not need Home Assistant at runtime. Stub only the two HA
# base classes imported by assistant.py so these tests stay quick and isolated.
ha = types.ModuleType("homeassistant")
ha.__path__ = []
components = types.ModuleType("homeassistant.components")
components.__path__ = []
sensor_module = types.ModuleType("homeassistant.components.sensor")
sensor_module.SensorEntity = type("SensorEntity", (), {})
helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []
storage_module = types.ModuleType("homeassistant.helpers.storage")
storage_module.Store = type("Store", (), {})
util_module = types.ModuleType("homeassistant.util")
util_module.__path__ = []
dt_module = types.ModuleType("homeassistant.util.dt")
dt_module.now = lambda: datetime.now(UTC)
util_module.dt = dt_module
sys.modules.update({
    "homeassistant": ha,
    "homeassistant.components": components,
    "homeassistant.components.sensor": sensor_module,
    "homeassistant.helpers": helpers,
    "homeassistant.helpers.storage": storage_module,
    "homeassistant.util": util_module,
    "homeassistant.util.dt": dt_module,
})

repo_root = Path(__file__).resolve().parents[1]
package = types.ModuleType("custom_components.discord_game")
package.__path__ = [str(repo_root / "custom_components" / "discord_game")]
sys.modules["custom_components.discord_game"] = package
assistant_module = importlib.import_module("custom_components.discord_game.assistant")
local_status_module = importlib.import_module("custom_components.discord_game.local_status")
local_tasks_module = importlib.import_module("custom_components.discord_game.local_tasks")
answer_local_status = local_status_module.answer_local_status
parse_local_reminder = local_tasks_module.parse_local_reminder

DiscordAssistant = assistant_module.DiscordAssistant
speech = assistant_module.speech


def test_legacy_sixty_message_threshold_migrates_to_eight_raw_messages(monkeypatch):
    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(assistant_module, "Store", FakeStore)
    assistant = DiscordAssistant(
        SimpleNamespace(), "entry", {"history_limit": 60}, None
    )

    assert assistant.history_limit == 8
    assert assistant.limit == 12


def test_custom_legacy_history_limit_is_preserved():
    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

    original_store = assistant_module.Store
    assistant_module.Store = FakeStore
    try:
        assistant = DiscordAssistant(
            SimpleNamespace(), "entry", {"history_limit": 35}, None
        )
    finally:
        assistant_module.Store = original_store

    assert assistant.history_limit == 35


def test_speech_extracts_home_assistant_plain_response():
    assert speech({"response": {"speech": {"plain": {"speech": "Hello"}}}}) == "Hello"


def test_speech_accepts_text_response():
    assert speech({"text": "Done"}) == "Done"


def test_prompt_keeps_current_request_when_it_exceeds_budget():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 4
    assistant.budget = 2000
    batch = [{
        "sender_name": "Max",
        "content": "PLEASE DO THIS FIRST: " + "x" * 2000 + "PLEASE KEEP THIS END",
        "is_dm": True,
    }]
    prompt = assistant._prompt(batch, [], "private contact summary")
    assert "PLEASE DO THIS FIRST" in prompt
    assert "PLEASE KEEP THIS END" in prompt
    assert len(prompt) <= assistant.budget
    assert "private contact summary" in prompt
    assert "You are GHOST" in prompt
    assert "under 30 words" in prompt
    assert "Do not use phonetic dialect" in prompt


def test_default_agent_prompts_are_northern_british_and_role_specific():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 8
    assistant.budget = 10000
    assistant.config = {}
    batch = [{"sender_name": "Max", "content": "Set the lights to full", "is_dm": True}]

    conversation = assistant._prompt(batch, [], "", role="conversation")
    operations = assistant._prompt(batch, [], "", role="operations")
    fallback = assistant._prompt(batch, [], "", role="advanced")

    assert "heavy dry sarcasm" in conversation
    assert "northern British" in conversation
    assert "must never impersonate them" in conversation
    assert "100 percent" in operations
    assert "available fields" in operations
    assert "do not retry an action" in operations.lower()
    assert "Break complex work into explicit steps" in fallback


def test_custom_agent_prompt_overrides_builtin_default():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 8
    assistant.budget = 10000
    assistant.config = {"operations_system_prompt": "My custom operations rules"}
    batch = [{"sender_name": "Max", "content": "Set the lights to full", "is_dm": True}]

    prompt = assistant._prompt(batch, [], "", role="operations")

    assert "My custom operations rules" in prompt
    assert "Built-in default instructions for this role" not in prompt


def test_prompt_uses_only_supplied_contact_history():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 10
    assistant.budget = 2000
    batch = [{"sender_name": "Ryan", "content": "Hello", "is_dm": True}]
    prompt = assistant._prompt(batch, [{"role": "user", "content": "Ryan's own history"}], "")
    assert "Ryan's own history" in prompt
    assert "Max's private history" not in prompt

def test_action_result_requires_home_assistant_action_done():
    assert assistant_module.action_result_error({"response": {"response_type": "action_done", "data": {"success": [{"id": "light.kitchen"}], "failed": []}}}) is None


def test_action_result_rejects_plain_speech_as_proof():
    error = assistant_module.action_result_error({"response": {"response_type": "success", "speech": {"plain": {"speech": "Done!"}}}})
    assert error and "completed Home Assistant action" in error


def test_action_result_reports_failed_targets():
    error = assistant_module.action_result_error({"response": {"response_type": "action_done", "data": {"success": [], "failed": [{"id": "light.kitchen"}]}}})
    assert error and "light.kitchen" in error


def test_action_result_rejects_empty_success_list():
    error = assistant_module.action_result_error({"response": {"response_type": "action_done", "data": {"success": [], "failed": []}}})
    assert error and "successfully completed" in error



def test_enqueue_rejects_empty_discord_messages():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.enabled = True
    assistant.stopped = False
    assistant.approved_users = {"456"}
    assistant.group_channels = set()
    assistant.transcript = []
    assistant.queue = []
    assistant.max_queue = 10
    assistant.wake = asyncio.Event()
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None))
    assistant.sensor = SimpleNamespace(hass=None)
    message = SimpleNamespace(
        id=987,
        content="   ",
        guild=None,
        channel=SimpleNamespace(id=123),
        created_at=datetime.now(UTC),
    )

    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Max"))

    assert assistant.queue == []


def test_enqueue_applies_backpressure_instead_of_dropping_oldest_message():

    fired = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.enabled = True
    assistant.stopped = False
    assistant.approved_users = {"456"}
    assistant.group_channels = set()
    assistant.transcript = []
    assistant.queue = [{"content": "earlier message"}]
    assistant.sender_activity = assistant_module.defaultdict(assistant_module.deque)
    assistant.spam_penalties = {}
    assistant.spam_window_seconds = 30
    assistant.spam_message_limit = 8
    assistant.spam_defer_minutes = 10
    assistant.spam_timeout_minutes = 5
    assistant.spam_policy = "defer_local"
    assistant.spam_local_agent = ""
    assistant.max_queue = 1
    assistant.wake = asyncio.Event()
    assistant.error = None
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(
        async_fire=lambda *args, **kwargs: fired.append((args, kwargs))
    ))
    assistant.sensor = SimpleNamespace(hass=None)
    message = SimpleNamespace(
        id=988,
        content="new message",
        guild=None,
        channel=SimpleNamespace(id=123),
        created_at=datetime.now(UTC),
    )

    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Max"))

    assert assistant.queue == [{"content": "earlier message"}]
    assert "queue is full" in assistant.error
    assert fired and fired[0][0][0] == "discord_game_assistant_error"




def test_enqueue_deduplicates_message_ids_already_queued_or_processed():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.enabled = True
    assistant.stopped = False
    assistant.approved_users = {"456"}
    assistant.group_channels = set()
    assistant.transcript = []
    assistant.queue = []
    assistant.sender_activity = assistant_module.defaultdict(assistant_module.deque)
    assistant.spam_penalties = {}
    assistant.spam_window_seconds = 30
    assistant.spam_message_limit = 8
    assistant.spam_defer_minutes = 10
    assistant.spam_timeout_minutes = 5
    assistant.spam_policy = "defer_local"
    assistant.spam_local_agent = ""
    assistant.max_queue = 10
    assistant.wake = asyncio.Event()
    assistant.contact_names = {}
    assistant.conversation_meta = {}
    assistant.conversation_logs = {"dm:456": []}
    assistant.conversation_history_limit = 100
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None))
    assistant.sensor = SimpleNamespace(hass=None)
    message = SimpleNamespace(
        id=989,
        content="Hello GHOST",
        guild=None,
        channel=SimpleNamespace(id=123, name="Direct message"),
        created_at=datetime.now(UTC),
        mentions=[],
        reference=None,
    )

    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Max"))
    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Max"))

    assert len(assistant.queue) == 1
    assert len(assistant.conversation_logs["dm:456"]) == 1

    assistant.queue.clear()
    assistant.transcript.append({
        "messages": [{"message_id": "989"}],
    })
    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Max"))
    assert assistant.queue == []


def test_enqueue_rejects_unapproved_direct_messages():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.enabled = True
    assistant.stopped = False
    assistant.approved_users = {"123"}
    assistant.group_channels = set()
    assistant.queue = []
    assistant.transcript = []
    message = SimpleNamespace(
        id=990,
        content="Do something",
        channel=SimpleNamespace(id=123),
    )

    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Unknown"))

    assert assistant.queue == []


def test_action_classifier_routes_home_assistant_operations():
    action = assistant_module.ACTION
    assert action.search("Set the bedroom lights to 30 percent")
    assert action.search("Remind me to call Max in ten minutes")
    assert action.search("Turn off the fan")
    assert action.search("Set the heating to 19 degrees")


def test_action_classifier_does_not_match_ordinary_chat():
    action = assistant_module.ACTION
    assert not action.search("What do you think of the new film?")
    assert not action.search("Tell me a joke")
    assert not action.search("Help me debug this automation")
    assert action.search("Run the bedroom lighting script")



def test_pause_resume_and_clear_queue_controls():

    events = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.paused = False
    assistant.queue = [{"content": "one"}, {"content": "two"}]
    assistant.error = "old error"
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(
        async_fire=lambda *args, **kwargs: events.append((args, kwargs))
    ))
    assistant.wake = asyncio.Event()

    asyncio.run(assistant.pause())
    assert assistant.paused is True

    asyncio.run(assistant.resume())
    assert assistant.paused is False
    assert assistant.wake.is_set()

    removed = asyncio.run(assistant.clear_queue())
    assert removed == 2
    assert assistant.queue == []
    assert assistant.error is None
    assert events[-1][0][0] == "discord_game_assistant_queue_cleared"



def test_complex_request_classifier_selects_advanced_model():
    assert assistant_module.COMPLEX_REQUEST.search("Research and compare three options")
    assert assistant_module.COMPLEX_REQUEST.search("Help me debug this automation")


def test_complex_request_classifier_ignores_simple_chat():
    assert not assistant_module.COMPLEX_REQUEST.search("What's the weather like?")



def test_model_usage_returns_persisted_per_agent_totals():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.model_usage_data = {
        "conversation.local": {
            "requests": 2, "input_tokens": 150, "output_tokens": 30, "errors": 0
        },
        "conversation.api": {
            "requests": 1, "input_tokens": 200, "output_tokens": 40, "errors": 1
        },
    }

    usage = assistant.model_usage()

    assert usage["conversation.local"] == {
        "requests": 2, "input_tokens": 150, "output_tokens": 30, "errors": 0
    }
    assert usage["conversation.api"] == {
        "requests": 1, "input_tokens": 200, "output_tokens": 40, "errors": 1
    }



def test_action_result_snapshot_keeps_success_and_failure_targets():
    snapshot = assistant_module.action_result_snapshot({
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"name": "Bedroom", "entity_id": "light.bedroom"}],
                "failed": [{"name": "Hall", "id": "light.hall", "error": "entity unavailable"}],
            },
        },
    })

    assert snapshot == {
        "response_type": "action_done",
        "success": [{"name": "Bedroom", "id": "light.bedroom"}],
        "failed": [{"name": "Hall", "id": "light.hall", "error": "entity unavailable"}],
    }



def test_admin_diagnostics_expose_paused_state_and_active_request():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.enabled = True
    assistant.paused = True
    assistant.approved_users = {"123"}
    assistant.group_channels = {"789"}
    assistant.queue = []
    assistant.active = False
    assistant.agents = {"conversation_agent": "conversation.local"}
    assistant.last_activity = None
    assistant.error = None
    assistant.transcript = []
    assistant.model_usage_data = {}
    assistant.active_request = {"conversation": "dm:123"}
    assistant.context_notes = {}
    assistant.friends = {}

    attributes = assistant.diagnostics()

    assert attributes["paused"] is True
    assert attributes["active_request"] == {"conversation": "dm:123"}



def test_queued_message_can_be_edited_and_cancelled_individually():

    events = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.queue = [{
        "message_id": "111",
        "key": "dm:123",
        "content": "original",
    }, {
        "message_id": "222",
        "key": "dm:456",
        "content": "keep this",
    }]
    assistant.conversation_logs = {
        "dm:123": [{"message_id": "111", "content": "original"}],
        "dm:456": [{"message_id": "222", "content": "keep this"}],
    }
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(
        async_fire=lambda *args, **kwargs: events.append((args, kwargs))
    ))

    edited = asyncio.run(assistant.edit_queued_message("111", "corrected"))
    assert edited is True
    assert assistant.queue[0]["content"] == "corrected"
    assert assistant.conversation_logs["dm:123"][0]["content"] == "corrected"

    cancelled = asyncio.run(assistant.cancel_queued_message("111"))
    assert cancelled is True
    assert len(assistant.queue) == 1
    assert assistant.queue[0]["message_id"] == "222"
    assert assistant.conversation_logs["dm:123"] == []
    assert events[0][0][0] == "discord_game_assistant_queue_edited"
    assert events[1][0][0] == "discord_game_assistant_queue_message_cancelled"


def test_editing_queue_rejects_blank_content():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.queue = [{"message_id": "111", "content": "original"}]

    with pytest.raises(ValueError, match="cannot be empty"):
        asyncio.run(assistant.edit_queued_message("111", "   "))



def test_transcript_replay_requeues_original_dm_messages():

    channel = SimpleNamespace(id=789)

    class FakeUser:
        async def create_dm(self):
            return channel

    class FakeBot:
        async def fetch_user(self, user_id):
            assert user_id == 123
            return FakeUser()

    events = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.transcript = [{
        "timestamp": "2026-11-14T00:00:00+00:00",
        "conversation": "dm:123",
        "is_dm": True,
        "sender_ids": ["123"],
        "sender": "Max",
        "channel_id": "789",
        "user_messages": ["Switch the bedroom light on"],
    }]
    assistant.queue = []
    assistant.max_queue = 200
    assistant.bot = FakeBot()
    assistant.approved_users = {"123"}
    assistant.group_channels = set()
    assistant.wake = asyncio.Event()
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(
        async_fire=lambda *args, **kwargs: events.append((args, kwargs))
    ))

    count = asyncio.run(assistant.replay_transcript(
        "2026-11-14T00:00:00+00:00", "dm:123"
    ))

    assert count == 1
    assert assistant.queue[0]["content"] == "Switch the bedroom light on"
    assert assistant.queue[0]["channel"] is channel
    assert assistant.wake.is_set()
    assert events[0][0][0] == "discord_game_assistant_replayed"



def test_prompt_changes_instructions_for_operations_and_advanced_roles():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 10
    assistant.budget = 2000
    batch = [{"sender_name": "Max", "content": "Turn on the bedroom light", "is_dm": True}]

    operations = assistant._prompt(batch, [], "", "operations")
    advanced = assistant._prompt(batch, [], "", "advanced")
    conversation = assistant._prompt(batch, [], "", "conversation")

    assert "operations agent" in operations
    assert "advanced reasoning agent" in advanced
    assert "ordinary conversation" in conversation



def test_admin_can_correct_contact_memory():

    saved = []
    class FakeStore:
        async def async_save(self, data):
            saved.append(data)

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {"123": {"messages": [{"content": "hello"}], "summary": "old summary"}}
    assistant.approved_users = {"123"}
    assistant.store = FakeStore()
    assistant.transcript = []
    assistant.model_usage_data = {}
    assistant.sensor = SimpleNamespace(hass=None)

    asyncio.run(assistant.set_friend_memory("123", "Corrected fact: Max prefers short replies."))

    assert assistant.friends["123"]["summary"] == "Corrected fact: Max prefers short replies."
    assert saved[0]["friends"]["123"]["summary"] == "Corrected fact: Max prefers short replies."


def test_admin_memory_correction_has_a_size_limit():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {}
    assistant.approved_users = {"123"}
    with pytest.raises(ValueError, match="4000 characters"):
        asyncio.run(assistant.set_friend_memory("123", "x" * 4001))



def test_memory_consolidates_without_a_configured_memory_model():
    saved = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {
        "123": {
            "summary": "",
            "messages": [{"role": "user", "content": "hello"}],
            "pending_messages": [{"role": "user", "content": "hello"}],
        },
        "456": {
            "summary": "Preference: likes tea",
            "messages": [],
            "pending_messages": [{"role": "user", "content": "I love tea"}],
        },
    }
    assistant.agents = {"memory_agent": ""}
    assistant.memory_batch_messages = 5
    assistant.history_limit = 2
    assistant.contact_names = {"123": "Max"}
    assistant.last_memory_consolidation = None
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None))

    async def save():
        saved.append(True)

    assistant._save = save
    result = asyncio.run(assistant._compress("123"))

    assert result is True
    assert assistant.friends["123"]["pending_messages"] == []
    assert assistant.friends["123"]["summary"] == ""
    assert assistant.friends["456"]["pending_messages"][0]["content"] == "I love tea"
    assert saved


def test_memory_consolidation_uses_only_explicit_facts_and_keeps_unprocessed_evidence():
    saved = []
    events = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {"123": {
        "summary": "Right, mate, what's on your mind? The lights are definitely red-ing this morning, proper shockin', innit?",
        "messages": [{"role": "user", "content": str(i)} for i in range(8)],
        "pending_messages": [
            {"role": "user", "sender": "Max", "content": "hello"},
            {"role": "user", "sender": "Max", "content": "I prefer comedy films"},
            {"role": "user", "sender": "Max", "content": "Remember that I use Home Assistant"},
        ],
    }}
    assistant.memory_batch_messages = 2
    assistant.history_limit = 1
    assistant.contact_names = {"123": "Max"}
    assistant.last_memory_consolidation = None
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(
        async_fire=lambda *args, **kwargs: events.append((args, kwargs))
    ))

    async def save():
        saved.append(True)

    assistant._save = save
    result = asyncio.run(assistant._consolidate_pending_memories())

    assert result == 1
    summary = assistant.friends["123"]["summary"]
    assert "Right, mate" not in summary
    assert "red-ing" not in summary
    assert "Preference: prefer comedy films" in summary
    assert "Explicitly remembered: I use Home Assistant" in summary
    assert len(assistant.friends["123"]["pending_messages"]) == 1
    assert assistant.friends["123"]["pending_messages"][0]["content"] == "hello"
    assert len(assistant.friends["123"]["messages"]) == 1
    assert saved and events


def test_memory_extractor_ignores_assistant_text_and_unverified_claims():
    facts = assistant_module.extract_durable_memory_facts([
        {"role": "assistant", "content": "The lights are definitely red this morning, mate."},
        {"role": "user", "content": "The lights are red."},
        {"role": "user", "content": "I love science fiction films."},
        {"role": "user", "content": "Remember that my server is called GHOST."},
    ])

    assert facts == [
        "Preference: love science fiction films",
        "Explicitly remembered: my server is called GHOST",
    ]


def test_memory_consolidation_does_not_need_a_memory_model():
    saved = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {"123": {
        "summary": "Preference: likes tea",
        "messages": [],
        "pending_messages": [{"role": "user", "content": "hello"}],
    }}
    assistant.memory_batch_messages = 5
    assistant.history_limit = 0
    assistant.contact_names = {"123": "Max"}
    assistant.last_memory_consolidation = None
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None))

    async def save():
        saved.append(True)

    assistant._save = save
    assert asyncio.run(assistant._consolidate_pending_memories()) == 1
    assert assistant.friends["123"]["summary"] == "Preference: likes tea"
    assert assistant.friends["123"]["pending_messages"] == []
    assert saved




def test_function_configuration_error_is_detected_for_fallback():
    assert assistant_module.is_function_configuration_error(
        "Something went wrong: failed to load functions. Verify functions are valid in a yaml format"
    )
    assert not assistant_module.is_function_configuration_error("I could not find that device.")


def test_api_group_relevance_refuses_to_use_tool_enabled_primary_agent():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = False
    assistant.group_relevance_agent = "conversation.api"
    assistant.agents = {"conversation_agent": "conversation.api"}
    assistant.limit = 8

    async def unexpected_call(*args):
        raise AssertionError("The API agent must not be used for group relevance")

    assistant._call = unexpected_call
    result = asyncio.run(assistant._should_respond_to_group(
        [{"sender_name": "Max", "content": "Hello", "directly_addressed": False}],
        [],
    ))
    assert result[0] is False
    assert "separate local agent" in result[1]


def test_api_group_relevance_uses_separate_local_model_without_mention():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = False
    assistant.group_relevance_agent = "conversation.local_relevance"
    assistant.agents = {"conversation_agent": "conversation.api", "fallback_agent": "conversation.api_fallback"}
    assistant.limit = 8
    calls = []

    async def classify(agent, prompt):
        calls.append(agent)
        assert "not required unless mention-only mode is enabled" in prompt
        return '{"respond": true, "reason": "The question invites GHOST to help"}'

    assistant._call = classify
    batch = [{"sender_name": "Ryan", "content": "Anyone know what time the heating turns off?", "directly_addressed": False}]
    should_respond, reason = asyncio.run(assistant._should_respond_to_group(batch, []))
    assert should_respond is True
    assert "invites GHOST" in reason
    assert calls == ["conversation.local_relevance"]


def test_group_mention_only_toggle_suppresses_unaddressed_without_model_call():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = True
    assistant.group_relevance_agent = "conversation.local_relevance"
    assistant.agents = {"conversation_agent": "conversation.api"}
    assistant.limit = 8

    async def unexpected_call(*args):
        raise AssertionError("Mention-only mode must bypass relevance inference")

    assistant._call = unexpected_call
    batch = [{"sender_name": "Ryan", "content": "Anyone know what time it is?", "directly_addressed": False}]
    should_respond, reason = asyncio.run(assistant._should_respond_to_group(batch, []))
    assert should_respond is False
    assert "mention-only" in reason


def test_group_mention_only_toggle_allows_explicit_address_without_model_call():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = True
    assistant.group_relevance_agent = "conversation.local_relevance"
    assistant.agents = {"conversation_agent": "conversation.api"}
    assistant.limit = 8

    async def unexpected_call(*args):
        raise AssertionError("Mention-only mode must bypass relevance inference")

    assistant._call = unexpected_call
    batch = [{"sender_name": "Ryan", "content": "Ghost, can you help?", "directly_addressed": True}]
    should_respond, reason = asyncio.run(assistant._should_respond_to_group(batch, []))
    assert should_respond is True
    assert "directly addressed" in reason


def test_group_relevance_gate_uses_ai_decision_before_reply():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.agents = {"conversation_agent": "conversation.local"}
    assistant.limit = 10

    async def classify(agent, prompt):
        assert agent == "conversation.local"
        assert "You are NOT writing a reply" in prompt
        assert "Recent conversation" in prompt
        return '{"respond": false, "reason": "This is banter between friends"}'

    assistant._call = classify
    batch = [{"sender_name": "Ryan", "content": "That was rubbish", "is_dm": False}]

    should_respond, reason = asyncio.run(
        assistant._should_respond_to_group(batch, [])
    )

    assert should_respond is False
    assert reason == "This is banter between friends"



def test_group_relevance_gate_uses_fallback_after_malformed_primary_output():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.agents = {
        "conversation_agent": "conversation.local",
        "fallback_agent": "conversation.backup",
    }
    assistant.limit = 8
    calls = []

    async def call(agent, prompt):
        calls.append(agent)
        if agent == "conversation.local":
            return "That is not JSON"
        return '{"respond": true, "reason": "Direct question"}'

    assistant._call = call
    batch = [{
        "sender_name": "Max",
        "content": "Can you help?",
        "directly_addressed": False,
    }]

    result = asyncio.run(assistant._should_respond_to_group(batch, []))

    assert result == (True, "Direct question")
    assert calls == ["conversation.local", "conversation.backup"]


def test_partial_action_error_names_successful_and_failed_targets():
    error = assistant_module.action_result_error({
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"name": "Bedroom", "id": "light.bedroom"}],
                "failed": [{"name": "Hall", "id": "light.hall"}],
            },
        },
    })

    assert "partially completed" in error
    assert "Bedroom" in error
    assert "Hall" in error



def test_group_relevance_gate_allows_a_relevant_direct_question():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.agents = {"conversation_agent": "conversation.local"}
    assistant.limit = 10

    async def classify(agent, prompt):
        return '{"respond": true, "reason": "GHOST was directly asked"}'

    assistant._call = classify
    batch = [{"sender_name": "Max", "content": "GHOST, can you check the lights?", "is_dm": False}]

    should_respond, reason = asyncio.run(
        assistant._should_respond_to_group(batch, [])
    )

    assert should_respond is True
    assert "directly asked" in reason


def test_group_relevance_gate_fails_silent_on_invalid_model_output():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.agents = {"conversation_agent": "conversation.local"}
    assistant.limit = 10

    async def classify(agent, prompt):
        return "Maybe I should say hello."

    assistant._call = classify
    batch = [{"sender_name": "Ryan", "content": "Hello Max", "is_dm": False}]

    should_respond, reason = asyncio.run(
        assistant._should_respond_to_group(batch, [])
    )

    assert should_respond is False
    assert "stayed quiet" in reason


def test_contact_memory_capture_is_per_approved_speaker_only():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.friends = {}
    assistant.contact_names = {"123": "Max"}
    assistant.limit = 10
    assistant.history_limit = 4

    assistant._capture_contact_messages([
        {"sender_id": "123", "sender_name": "Max", "content": "I like strategy games", "timestamp": "1", "key": "guild:5:7"},
        {"sender_id": "456", "sender_name": "Unknown", "content": "private detail", "timestamp": "2", "key": "guild:5:7"},
    ])

    assert len(assistant.friends["123"]["pending_messages"]) == 1
    assert assistant.friends["123"]["pending_messages"][0]["content"] == "I like strategy games"
    assert "456" not in assistant.friends


def test_manual_dm_send_rejects_unapproved_user():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.approved_users = {"123"}

    with pytest.raises(ValueError, match="not on the approved"):
        asyncio.run(assistant.send_manual(message="Hello", user_id="456"))


def test_manual_channel_send_rejects_unselected_channel():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.approved_users = {"123"}
    assistant.group_channels = {"789"}

    with pytest.raises(ValueError, match="not enabled for GHOST"):
        asyncio.run(assistant.send_manual(message="Hello", channel_id="456"))



def test_context_audit_keeps_ten_newest_prompts_complete():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.transcript = [
        {"context_snapshot": "x" * 5000}
        for _ in range(12)
    ]

    assistant._trim_context_snapshots()

    assert len(assistant.transcript[0]["context_snapshot"]) < 5000
    assert len(assistant.transcript[1]["context_snapshot"]) < 5000
    assert len(assistant.transcript[2]["context_snapshot"]) == 5000
    assert len(assistant.transcript[-1]["context_snapshot"]) == 5000



def test_model_call_tracks_per_agent_estimated_usage():

    class FakeServices:
        async def async_call(self, domain, service, data, blocking, return_response):
            assert domain == "conversation"
            assert service == "process"
            assert data["agent_id"] == "conversation.local"
            assert blocking is True
            assert return_response is True
            return {"response": {"speech": {"plain": {"speech": "Hello"}}}}

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.hass = SimpleNamespace(services=FakeServices())
    assistant.model_usage_data = {}

    answer = asyncio.run(assistant._call("conversation.local", "x" * 40))

    assert answer == "Hello"
    assert assistant.model_usage_data["conversation.local"] == {
        "requests": 1, "input_tokens": 10, "output_tokens": 1, "errors": 0
    }


def test_model_call_counts_provider_errors():

    class FakeServices:
        async def async_call(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.hass = SimpleNamespace(services=FakeServices())
    assistant.model_usage_data = {}

    with pytest.raises(RuntimeError, match="provider unavailable"):
        asyncio.run(assistant._call("conversation.local", "hello"))

    assert assistant.model_usage_data["conversation.local"]["errors"] == 1



def test_manual_send_rejects_two_destinations():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    with pytest.raises(ValueError, match="not both"):
        asyncio.run(assistant.send_manual(
            message="Hello", user_id="123", channel_id="789"
        ))



def test_action_retry_requires_explicit_structured_failed_entity():
    result = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [],
                "failed": [{
                    "entity_id": "light.hall",
                    "error": "Service rejected the target",
                }],
            },
        },
    }

    assert assistant_module.action_result_retryable(result)
    assert assistant_module.action_retry_targets(result) == ["light.hall"]


def test_action_retry_scopes_partial_failure_to_failed_targets_only():
    result = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"entity_id": "light.bedroom"}],
                "failed": [{
                    "entity_id": "light.hall",
                    "error": "Target rejected",
                }],
            },
        },
    }

    assert assistant_module.action_result_retryable(result)
    assert assistant_module.action_retry_targets(result) == ["light.hall"]
    assert "light.bedroom" not in assistant_module.action_retry_targets(result)


def test_action_retry_is_blocked_for_ambiguous_or_unscoped_failures():
    assert not assistant_module.action_result_retryable(RuntimeError("timeout"))
    assert not assistant_module.action_result_retryable({
        "response": {"response_type": "success", "speech": {"plain": {"speech": "Done"}}}
    })
    assert not assistant_module.action_result_retryable({
        "response": {
            "response_type": "action_done",
            "data": {"success": [], "failed": []},
        },
    })
    assert not assistant_module.action_result_retryable({
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [],
                "failed": [{"name": "Hall", "error": "Target rejected"}],
            },
        },
    })
    assert not assistant_module.action_result_retryable({
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [],
                "failed": [{"entity_id": "light.hall"}],
            },
        },
    })


def test_action_retry_merge_preserves_first_success_and_uses_retry_outcome():
    first = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"entity_id": "light.bedroom"}],
                "failed": [{"entity_id": "light.hall", "error": "Rejected"}],
            },
        },
    }
    retry = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"entity_id": "light.hall"}],
                "failed": [],
            },
        },
    }

    merged = assistant_module.merge_action_retry_results(first, retry)

    assert merged["response"]["data"]["success"] == [
        {"entity_id": "light.bedroom"},
        {"entity_id": "light.hall"},
    ]
    assert merged["response"]["data"]["failed"] == []
    assert assistant_module.action_result_error(merged) is None


def test_action_retry_merge_rejects_empty_or_incomplete_retry_results():
    first = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [],
                "failed": [
                    {"entity_id": "light.hall", "error": "Rejected"},
                    {"entity_id": "light.kitchen", "error": "Rejected"},
                ],
            },
        },
    }
    empty_retry = {
        "response": {
            "response_type": "action_done",
            "data": {"success": [], "failed": []},
        },
    }
    incomplete_retry = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"entity_id": "light.hall"}],
                "failed": [],
            },
        },
    }

    assert assistant_module.merge_action_retry_results(first, empty_retry) is None
    assert assistant_module.merge_action_retry_results(first, incomplete_retry) is None


def test_action_retry_merge_rejects_targets_outside_failed_set():
    first = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [],
                "failed": [{"entity_id": "light.hall", "error": "Rejected"}],
            },
        },
    }
    retry = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"entity_id": "light.hall"}, {"entity_id": "light.bedroom"}],
                "failed": [],
            },
        },
    }

    assert assistant_module.merge_action_retry_results(first, retry) is None


def test_controlled_action_retry_calls_once_and_only_targets_failed_entities():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.active_request = None
    assistant._last_call_result = None
    calls = []

    async def call(agent, prompt):
        calls.append((agent, prompt))
        assistant._last_call_result = {
            "response": {
                "response_type": "action_done",
                "data": {
                    "success": [{"entity_id": "light.hall"}],
                    "failed": [],
                },
            },
        }
        return "The failed target is now on."

    assistant._call = call
    first = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"entity_id": "light.bedroom"}],
                "failed": [{"entity_id": "light.hall", "error": "Rejected"}],
            },
        },
    }
    attempted = []

    answer, merged = asyncio.run(assistant._retry_failed_action(
        "conversation.operations", "Original request: turn on both lights", first, attempted
    ))

    assert answer == "The failed target is now on."
    assert len(calls) == 1
    assert attempted == ["conversation.operations"]
    retry_instructions = calls[0][1].split("CONTROLLED ACTION RETRY", 1)[1]
    assert "light.hall" in retry_instructions
    assert "light.bedroom" not in retry_instructions
    assert merged["response"]["data"]["success"] == [
        {"entity_id": "light.bedroom"},
        {"entity_id": "light.hall"},
    ]


def test_controlled_action_retry_does_not_retry_again_after_retry_exception():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.active_request = None
    calls = []

    async def call(agent, prompt):
        calls.append(agent)
        raise RuntimeError("retry timed out")

    assistant._call = call
    first = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [],
                "failed": [{"entity_id": "light.hall", "error": "Rejected"}],
            },
        },
    }

    with pytest.raises(RuntimeError, match="retry timed out"):
        asyncio.run(assistant._retry_failed_action(
            "conversation.operations", "Original request", first, []
        ))

    assert calls == ["conversation.operations"]


def test_action_retry_merge_rejects_unstructured_retry_response():
    first = {
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [],
                "failed": [{"entity_id": "light.hall", "error": "Rejected"}],
            },
        },
    }

    assert assistant_module.merge_action_retry_results(first, {"response": {
        "response_type": "success",
        "speech": {"plain": {"speech": "Done"}},
    }}) is None


def test_model_call_does_not_retry_completed_action_without_speech():

    class FakeServices:
        async def async_call(self, *args, **kwargs):
            return {
                "response": {
                    "response_type": "action_done",
                    "data": {"success": [{"id": "light.bedroom"}], "failed": []},
                },
            }

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.hass = SimpleNamespace(services=FakeServices())
    assistant.model_usage_data = {}

    answer = asyncio.run(assistant._call("conversation.operations", "Turn on the light"))

    assert "action completed" in answer
    assert assistant_module.action_result_error(assistant._last_call_result) is None



def test_admin_cannot_create_memory_for_unapproved_contact():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {}
    assistant.approved_users = {"123"}

    with pytest.raises(ValueError, match="approved GHOST contacts"):
        asyncio.run(assistant.set_friend_memory("456", "Unapproved memory"))



def test_group_transcript_replay_preserves_each_sender():

    channel = SimpleNamespace(id=789)

    class FakeBot:
        def get_channel(self, channel_id):
            assert channel_id == 789
            return channel

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.transcript = [{
        "timestamp": "2026-11-14T00:00:00+00:00",
        "conversation": "guild:555:789",
        "is_dm": False,
        "sender_ids": ["123", "456"],
        "sender": "Max, Ryan",
        "channel_id": "789",
        "user_messages": ["First message", "Second message"],
        "messages": [
            {"sender": "Max", "sender_id": "123", "content": "First message"},
            {"sender": "Ryan", "sender_id": "456", "content": "Second message"},
        ],
    }]
    assistant.queue = []
    assistant.max_queue = 200
    assistant.bot = FakeBot()
    assistant.approved_users = {"123", "456"}
    assistant.group_channels = {"789"}
    assistant.wake = asyncio.Event()
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None))

    asyncio.run(assistant.replay_transcript(
        "2026-11-14T00:00:00+00:00", "guild:555:789"
    ))

    assert [item["sender_name"] for item in assistant.queue] == ["Max", "Ryan"]
    assert [item["sender_id"] for item in assistant.queue] == ["123", "456"]



def test_group_context_keeps_each_speaker_name():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 10
    assistant.budget = 2000
    batch = [{"sender_name": "Ryan", "content": "Current message", "is_dm": False}]
    history = [{"role": "user", "sender": "Max", "content": "Earlier group message"}]

    prompt = assistant._prompt(batch, history, "")

    assert "Max: Earlier group message" in prompt
    assert "Ryan: Current message" in prompt



def test_admin_can_inject_temporary_context_for_approved_dm():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.approved_users = {"123"}
    assistant.group_channels = {"789"}
    assistant.context_notes = {}
    assistant.sensor = SimpleNamespace(hass=None)

    asyncio.run(assistant.set_context_note("dm:123", "Max is currently testing the new reminder flow."))

    assert assistant.context_notes["dm:123"] == "Max is currently testing the new reminder flow."


def test_admin_can_inject_temporary_context_for_selected_group_channel():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.approved_users = {"123"}
    assistant.group_channels = {"789"}
    assistant.context_notes = {}
    assistant.sensor = SimpleNamespace(hass=None)

    asyncio.run(assistant.set_context_note("guild:555:789", "This channel is the game-night chat."))

    assert assistant.context_notes["guild:555:789"] == "This channel is the game-night chat."


def test_admin_cannot_inject_context_into_unapproved_conversation():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.approved_users = {"123"}
    assistant.group_channels = {"789"}
    assistant.context_notes = {}

    with pytest.raises(ValueError, match="approved GHOST DMs"):
        asyncio.run(assistant.set_context_note("dm:456", "Do not store this"))


def test_temporary_context_is_included_in_model_prompt():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 10
    assistant.budget = 3000
    batch = [{"sender_name": "Max", "content": "Hello", "is_dm": True}]

    prompt = assistant._prompt(batch, [], "", context_note="Max is testing the new reminder flow.")

    assert "Administrator-provided context" in prompt
    assert "Max is testing the new reminder flow." in prompt



def test_prompt_budget_includes_injected_context_and_durable_memory():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.limit = 10
    assistant.budget = 2000
    batch = [{
        "sender_name": "Max",
        "content": "Please carry out this task " + "x" * 2000,
        "is_dm": True,
    }]

    prompt = assistant._prompt(
        batch,
        [],
        "durable memory " * 500,
        "operations",
        "temporary context " * 500,
    )

    assert len(prompt) <= assistant.budget
    assert "Private memory for this approved DM contact" in prompt
    assert "Administrator-provided context" in prompt
    assert "Please carry out this task" in prompt



def test_public_sensor_attributes_do_not_expose_private_memory_or_transcript():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.enabled = True
    assistant.paused = False
    assistant.diagnostics_revision = 1
    assistant.queue = [{"content": "private incoming message"}]
    assistant.active = False
    assistant.last_activity = None
    assistant.error = None
    assistant.agents = {"conversation_agent": "conversation.local"}

    attributes = assistant.public_attributes()

    assert attributes["queue_length"] == 1
    assert "friend_memory" not in attributes
    assert "transcript" not in attributes
    assert "pending_messages" not in attributes
    assert "context_notes" not in attributes
    assert "approved_users" not in attributes
    assert "group_channels" not in attributes



def test_action_classifier_routes_natural_turn_device_on_phrasing():
    assert assistant_module.ACTION.search("Turn the bedroom light on")
    assert assistant_module.ACTION.search("Turn my desk lamp off")


def test_conversation_history_is_private_and_bounded():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.group_channels = {"789"}
    assistant.conversation_history_limit = 2
    assistant.conversation_logs = {"dm:123": [
        {"role": "user", "content": "old", "timestamp": "1"},
        {"role": "assistant", "content": "middle", "timestamp": "2"},
        {"role": "user", "content": "latest", "timestamp": "3"},
    ]}
    assistant.conversation_meta = {"dm:123": {"label": "Max"}}

    result = assistant.conversation_messages("dm:123")
    assert [item["content"] for item in result["messages"]] == ["middle", "latest"]

    with pytest.raises(ValueError, match="not approved"):
        assistant.conversation_messages("dm:456")


def test_diagnostics_use_friendly_names_and_include_empty_friend_threads():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.enabled = True
    assistant.paused = False
    assistant.approved_users = {"123"}
    assistant.group_channels = set()
    assistant.queue = []
    assistant.active = False
    assistant.agents = {"conversation_agent": "conversation.local"}
    assistant.last_activity = None
    assistant.error = None
    assistant.transcript = []
    assistant.model_usage_data = {}
    assistant.active_request = None
    assistant.context_notes = {}
    assistant.friends = {}
    assistant.contact_names = {"123": "Max"}

    result = assistant.diagnostics()
    assert result["contacts"][0]["name"] == "Max"
    assert result["conversations"][0]["label"] == "Max"
    assert result["conversations"][0]["message_count"] == 0


def test_newly_approved_friend_can_open_an_empty_conversation():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.group_channels = set()
    assistant.conversation_history_limit = 100
    assistant.conversation_logs = {}
    assistant.conversation_meta = {}

    result = assistant.conversation_messages("dm:123")
    assert result["messages"] == []



def test_memory_pipeline_uses_deterministic_evidence_instead_of_a_model_prompt():
    assert "memory" not in assistant_module.DEFAULT_AGENT_PROMPTS
    assert assistant_module.extract_durable_memory_facts([
        {"role": "assistant", "content": "The lights are red, mate."},
        {"role": "user", "content": "The lights are red."},
    ]) == []


def test_action_outcome_memory_records_unconfirmed_not_success():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.friends = {}
    item = {"is_dm": True, "sender_id": "123"}
    assistant._capture_action_outcome_for_memory(
        item,
        "Set the room lights to maximum brightness",
        {"response_type": "action_done", "success": [], "failed": []},
        "No successful targets were reported",
    )
    event = assistant.friends["123"]["pending_messages"][0]
    assert event["role"] == "system_event"
    assert '"status":"NOT CONFIRMED:' in event["content"]
    assert '"success":[]' in event["content"]
    assert "Set the room lights to maximum brightness" in event["content"]


def test_action_outcome_memory_records_confirmed_success_only_from_target_list():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.friends = {}
    assistant._capture_action_outcome_for_memory(
        {"is_dm": True, "sender_id": "123"},
        "Turn on the bedroom light",
        {"response_type": "action_done", "success": [{"id": "light.bedroom"}], "failed": []},
    )
    event = assistant.friends["123"]["pending_messages"][0]
    assert '"status":"CONFIRMED:' in event["content"]


def test_action_outcome_memory_ignores_unapproved_and_group_messages():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.friends = {}
    assistant._capture_action_outcome_for_memory(
        {"is_dm": True, "sender_id": "456"}, "action", None
    )
    assistant._capture_action_outcome_for_memory(
        {"is_dm": False, "sender_id": "123"}, "action", None
    )
    assert assistant.friends == {}



def test_backfill_recovers_old_unconfirmed_action_from_transcript_once():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.friends = {}
    assistant.transcript = [{
        "timestamp": "2026-11-14T07:00:00+00:00",
        "conversation": "dm:123",
        "is_dm": True,
        "sender_ids": ["123"],
        "user_messages": ["Set the room lights to maximum brightness"],
        "error": "Action not confirmed",
        "action_result": {
            "response_type": "action_done",
            "success": [],
            "failed": [],
        },
    }]

    assistant._backfill_action_outcomes_from_transcript()
    assistant._backfill_action_outcomes_from_transcript()

    record = assistant.friends["123"]
    assert len(record["pending_messages"]) == 1
    assert '"status":"NOT CONFIRMED:' in record["pending_messages"][0]["content"]
    assert len(record["action_event_keys"]) == 1



def test_action_classifier_routes_colour_changes_to_operations():
    action = assistant_module.ACTION
    assert action.search("could you change the lights?")
    assert action.search("i want them red")
    assert action.search("set the rooms brightness to 50%")


def test_request_kind_separates_actions_queries_and_conversation():
    assert assistant_module.request_kind("Set the room brightness to 50%") == "action"
    assert assistant_module.request_kind("I want the lights red") == "action"
    assert assistant_module.request_kind("What's Harvey doing right now?") == "query"
    assert assistant_module.request_kind("What's the current state of the room lights?") == "query"
    assert assistant_module.request_kind("What are the lights set to?") == "query"
    assert assistant_module.request_kind("Could you set the lights to red?") == "action"
    assert assistant_module.request_kind("What's Harvey doing? Also, change the lights to red.") == "action"
    assert assistant_module.request_kind("What do you think of this film?") == "conversation"


def test_conversation_batch_coalesces_interleaved_messages_without_crossing_users():
    queue = [
        {"key": "dm:1", "sort": 1, "content": "first"},
        {"key": "dm:2", "sort": 2, "content": "other person"},
        {"key": "dm:1", "sort": 3, "content": "second"},
        {"key": "guild:3:4", "sort": 4, "content": "group"},
    ]

    batch = assistant_module.take_conversation_batch(queue)

    assert [item["content"] for item in batch] == ["first", "second"]
    assert [item["content"] for item in queue] == ["other person", "group"]



def test_live_state_classifier_routes_presence_questions_to_operations():
    query = assistant_module.LIVE_STATE_QUERY
    assert query.search("whats Harvey doing right now?")
    assert query.search("what is the current status of the bedroom?")
    assert query.search("is Harvey home?")



def test_legacy_memory_cleanup_removes_assistant_banter_and_unverified_claims():
    legacy = """
    Ooh right, Harvey's doing nothing, just chillin' at full brightness mate.
    Harvey is definitely sat at his PC.
    Preference: like science fiction films
    Action record (NOT CONFIRMED): Turn the room lights red
    """
    cleaned = assistant_module.sanitize_legacy_memory_summary(legacy)
    assert "Ooh right" not in cleaned
    assert "definitely sat at his PC" not in cleaned
    assert "Preference: like science fiction films" in cleaned
    assert "Action record (NOT CONFIRMED): Turn the room lights red" in cleaned


def test_api_mode_prompt_keeps_ghost_memory_without_overriding_ha_agent_prompt():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.limit = 8
    assistant.budget = 4000
    batch = [{"sender_name": "Tokyo", "content": "What is Harvey doing?", "is_dm": True}]

    prompt = assistant._prompt(
        batch,
        [{"role": "user", "sender": "Tokyo", "content": "Earlier question"}],
        "- Preference: likes science fiction films",
        role="operations",
    )

    assert "Preference: likes science fiction films" in prompt
    assert "What is Harvey doing?" in prompt
    assert "Earlier question" in prompt
    assert "GHOST reference context" in prompt
    assert "Role instructions" not in prompt
    assert "You are GHOST:" not in prompt


def test_api_mode_prompt_does_not_include_another_contact_memory():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.limit = 8
    assistant.budget = 4000
    prompt = assistant._prompt(
        [{"sender_name": "Tokyo", "content": "Hello", "is_dm": True}],
        [],
        "",
        role="conversation",
    )
    assert "private memory" not in prompt.lower()
    assert "Saved facts about this approved DM contact" not in prompt



def test_local_reminder_parser_handles_relative_duration():
    parsed = parse_local_reminder(
        "Remind me to take the bins out in 20 minutes",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert parsed == {"name": "take the bins out", "duration_seconds": 1200}


def test_local_reminder_parser_handles_duration_before_task():

    parsed = parse_local_reminder(
        "Remind me in two hours to call Max",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert parsed == {"name": "call Max", "duration_seconds": 7200}


def test_local_reminder_parser_handles_spoken_tens():
    parsed = parse_local_reminder(
        "Remind me to call Max in twenty minutes",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert parsed == {"name": "call Max", "duration_seconds": 1200}


def test_local_reminder_parser_handles_explicit_date_and_clock_time():

    parsed = parse_local_reminder(
        "Remind me to take the bins out tomorrow at 7pm",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert parsed == {"name": "take the bins out", "alarm_time": "19:00", "date": "2026-11-15"}


def test_local_reminder_parser_asks_instead_of_guessing_ambiguous_time():

    parsed = parse_local_reminder(
        "Remind me to call Max at 7",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert parsed["needs_clarification"] is True
    assert "AM or PM" in parsed["clarification"]


def test_local_reminder_parser_requires_a_time():

    parsed = parse_local_reminder(
        "Remind me to call Max",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert parsed["needs_clarification"] is True
    assert "When should I remind you" in parsed["clarification"]


def test_local_status_reader_uses_discord_presence_sensor():
    state = SimpleNamespace(
        entity_id="sensor.discord_user_123",
        state="online",
        attributes={"friendly_name": "Harvey", "display_name": "Harvey", "game": "Factorio"},
    )
    hass = SimpleNamespace(states=SimpleNamespace(async_all=lambda: [state]))
    answer = answer_local_status(
        hass, "What's Harvey doing?",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert answer == "Harvey is playing Factorio."


def test_local_status_reader_reports_missing_weather_without_inventing_it():

    hass = SimpleNamespace(states=SimpleNamespace(async_all=list))
    answer = answer_local_status(
        hass, "What's the weather and current time?",
        datetime(2026, 11, 14, 9, 5, tzinfo=UTC),
    )
    assert "Saturday 09:05" in answer
    assert "can't see a Home Assistant weather entity" in answer



def test_local_reminder_executor_requires_script_success_response():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.local_reminder_script = "script.set_timer_alarm_or_reminder"

    class FakeServices:
        def has_service(self, domain, service):
            return (domain, service) == ("script", "set_timer_alarm_or_reminder")

        async def async_call(self, domain, service, data, **kwargs):
            assert domain == "script"
            assert service == "set_timer_alarm_or_reminder"
            assert data == {"name": "take bins out", "duration_seconds": 1200}
            assert kwargs == {"blocking": True, "return_response": True}
            return {"success": True, "name": "take bins out", "kind": "reminder"}

    assistant.hass = SimpleNamespace(services=FakeServices())
    result = asyncio.run(assistant._execute_local_reminder({
        "name": "take bins out", "duration_seconds": 1200
    }))
    assert assistant_module.action_result_error(result) is None
    snapshot = assistant_module.action_result_snapshot(result)
    assert snapshot["success"][0]["id"] == "script.set_timer_alarm_or_reminder"


def test_local_reminder_executor_does_not_claim_success_without_success_flag():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.local_reminder_script = "script.set_timer_alarm_or_reminder"

    class FakeServices:
        def has_service(self, domain, service):
            return True

        async def async_call(self, *args, **kwargs):
            return {"message": "The script did not return its success flag"}

    assistant.hass = SimpleNamespace(services=FakeServices())
    result = asyncio.run(assistant._execute_local_reminder({
        "name": "take bins out", "duration_seconds": 1200
    }))
    assert assistant_module.action_result_error(result) is not None



def test_local_status_reader_recovers_a_minor_contact_name_typo():
    state = SimpleNamespace(
        entity_id="sensor.discord_user_123",
        state="online",
        attributes={"friendly_name": "Harvey", "display_name": "Harvey", "game": "Factorio"},
    )
    hass = SimpleNamespace(states=SimpleNamespace(async_all=lambda: [state]))
    answer = answer_local_status(
        hass, "What's ahrveys doing?",
        datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
    )
    assert answer == "Harvey is playing Factorio."


def test_local_status_intent_recognises_time_weather_and_informal_presence_questions():
    assert assistant_module.request_kind("What's the current time and weather?") == "query"
    assert assistant_module.request_kind("Can you tell me what ahrveys doing?") == "query"
    assert assistant_module.request_kind("The weather is rubbish today") == "conversation"




def test_followup_classifier_recognises_context_dependent_replies():
    assert assistant_module.is_contextual_followup("you fixed yourself?")
    assert assistant_module.is_contextual_followup("what do you mean?")
    assert assistant_module.is_contextual_followup("and?")
    assert not assistant_module.is_contextual_followup("Anyone fancy a game tonight?")
    assert not assistant_module.is_contextual_followup("x" * 300)


def test_group_relevance_continues_recent_same_sender_thread_without_model_call():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = False
    assistant.group_continuity_seconds = 300
    assistant.group_relevance_agent = "conversation.local_relevance"
    assistant.agents = {"conversation_agent": "conversation.api"}
    assistant.limit = 8

    async def unexpected(*args):
        raise AssertionError("Should continue the recent thread without another relevance call")

    assistant._call = unexpected
    history = [
        {"role": "user", "sender": "Tokyo", "sender_id": "123", "content": "so what cunt, you fixed yourself yet?", "timestamp": "2026-11-14T11:44:00+00:00"},
        {"role": "assistant", "sender": "GHOST", "content": "What do you need help with?", "timestamp": "2026-11-14T11:45:00+00:00"},
    ]
    result = asyncio.run(assistant._should_respond_to_group(
        [{"sender_name": "Tokyo", "sender_id": "123", "content": "you fixed yourself?", "timestamp": "2026-11-14T11:45:10+00:00", "directly_addressed": False}],
        history,
    ))
    assert result[0] is True
    assert "follow-up" in result[1]


def test_group_continuity_does_not_cross_speakers_or_expire():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = False
    assistant.group_continuity_seconds = 60
    assistant.group_relevance_agent = ""
    assistant.agents = {"conversation_agent": "conversation.api"}
    assistant.limit = 8

    async def reject(*args):
        return '{"respond": false, "reason": "unrelated"}'

    assistant._call = reject
    history = [
        {"role": "user", "sender": "Tokyo", "sender_id": "123", "content": "so what?", "timestamp": "2026-11-14T11:44:00+00:00"},
        {"role": "assistant", "sender": "GHOST", "content": "What do you need help with?", "timestamp": "2026-11-14T11:45:00+00:00"},
    ]
    other = asyncio.run(assistant._should_respond_to_group(
        [{"sender_name": "Max", "sender_id": "456", "content": "you fixed yourself?", "timestamp": "2026-11-14T11:45:10+00:00"}], history))
    expired = asyncio.run(assistant._should_respond_to_group(
        [{"sender_name": "Tokyo", "sender_id": "123", "content": "you fixed yourself?", "timestamp": "2026-11-14T11:50:00+00:00"}], history))
    assert other[0] is False
    assert expired[0] is False


def test_memory_deduplication_is_case_and_punctuation_insensitive():
    result = assistant_module.deduplicate_memory_lines([
        "Preference: likes sci-fi films",
        "- preference: likes sci-fi films!",
        "Work: at a warehouse",
    ])
    assert result == ["Preference: likes sci-fi films", "Work: at a warehouse"]


def test_memory_replaceable_keys_supersede_work_and_same_favourite_category():
    assert assistant_module.replaceable_memory_key("Work: at a warehouse") == "work"
    assert assistant_module.replaceable_memory_key("Favourite: film — Interstellar") == "favourite:film"



def test_memory_consolidation_deduplicates_and_supersedes_old_work_and_favourite():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.friends = {
        "123": {
            "summary": "Work: at the old shop\nWork: at the old shop\nFavourite: film — Old Film",
            "summary_source": "legacy",
            "pending_messages": [{
                "role": "user",
                "content": "I work at the new shop. My favourite film is New Film",
            }],
            "messages": [],
        }
    }
    assistant.memory_batch_messages = 20
    assistant.history_limit = 8
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None))
    assistant._save = lambda: asyncio.sleep(0)
    assistant._refresh_sensor = lambda: None
    completed = asyncio.run(assistant._consolidate_pending_memories({"123"}))
    summary = assistant.friends["123"]["summary"]
    assert completed == 1
    assert summary.count("Work: at the new shop") == 1
    assert "Work: at the old shop" not in summary
    assert "Favourite: film — New Film" in summary
    assert "Old Film" not in summary
    assert assistant.friends["123"]["pending_messages"] == []


def test_group_history_is_restored_from_persisted_conversation_logs(monkeypatch):
    saved = {
        "friends": {},
        "transcript": [],
        "model_usage": {},
        "conversation_logs": {
            "guild:1:2": [
                {"role": "user", "sender": "Tokyo", "sender_id": "123", "content": "hello", "timestamp": "2026-11-14T11:44:00+00:00"},
                {"role": "assistant", "sender": "GHOST", "content": "What do you need help with?", "timestamp": "2026-11-14T11:45:00+00:00"},
            ],
        },
        "conversation_meta": {},
    }

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        async def async_load(self):
            return saved

    monkeypatch.setattr(assistant_module, "Store", FakeStore)
    assistant = DiscordAssistant(SimpleNamespace(), "entry", {"assistant_enabled": False}, None)
    assistant._refresh_sensor = lambda: None
    asyncio.run(assistant.async_start())
    assert [message["role"] for message in assistant.groups["guild:1:2"]] == ["user", "assistant"]
    assert assistant.groups["guild:1:2"][-1]["content"] == "What do you need help with?"


def test_memory_purge_refuses_to_race_an_active_private_conversation():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.friends = {"123": {"summary": "Preference: likes tea", "pending_messages": [], "messages": []}}
    assistant.active_request = {"conversation": "dm:123"}
    with pytest.raises(RuntimeError, match="being processed"):
        asyncio.run(assistant.purge_friend_memory("123", "all"))


def test_memory_purge_scopes_preserve_unselected_data():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.approved_users = {"123"}
    assistant.friends = {"123": {"summary": "Preference: likes tea", "pending_messages": [{"content": "remember this"}], "messages": [{"content": "hello"}]}}
    assistant.conversation_logs = {"dm:123": [{"content": "hello"}], "guild:1:2": [{"content": "group"}]}
    assistant.queue = [{"key": "dm:123", "message_id": "pending"}]
    assistant.context_notes = {"dm:123": "temporary"}
    assistant.active_request = None
    assistant.transcript = [{"is_dm": True, "sender_ids": ["123"]}, {"is_dm": False, "sender_ids": []}]
    assistant._save = lambda: asyncio.sleep(0)
    assistant._refresh_sensor = lambda: None
    asyncio.run(assistant.purge_friend_memory("123", "facts"))
    assert assistant.friends["123"]["summary"] == ""
    assert assistant.friends["123"]["pending_messages"]
    assert assistant.conversation_logs["dm:123"]
    asyncio.run(assistant.purge_friend_memory("123", "history"))
    assert assistant.friends["123"]["pending_messages"]
    assert "dm:123" not in assistant.conversation_logs
    assert not assistant.queue
    assert "dm:123" not in assistant.context_notes
    assert len(assistant.transcript) == 1
    asyncio.run(assistant.purge_friend_memory("123", "all"))
    assert "123" not in assistant.friends


def test_api_mode_mention_only_setting_prevents_untrusted_group_text_reaching_api_agent():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = True

    ignored = asyncio.run(assistant._should_respond_to_group(
        [{"directly_addressed": False, "sender_name": "Tokyo", "content": "Turn the lights red"}],
        [],
    ))
    allowed = asyncio.run(assistant._should_respond_to_group(
        [{"directly_addressed": True, "sender_name": "Tokyo", "content": "GHOST, turn the lights red"}],
        [],
    ))

    assert ignored[0] is False
    assert allowed[0] is True

def test_api_mode_uses_separate_api_fallback_agent(monkeypatch):
    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(assistant_module, "Store", FakeStore)
    assistant = DiscordAssistant(
        SimpleNamespace(),
        "entry",
        {
            "assistant_mode": "api",
            "conversation_agent": "conversation.openai_primary",
            "api_fallback_agent": "conversation.openai_fallback",
            "fallback_agent": "conversation.old_local_fallback",
        },
        None,
    )

    assert assistant.agents["conversation_agent"] == "conversation.openai_primary"
    assert assistant.agents["operations_agent"] == "conversation.openai_primary"
    assert assistant.agents["fallback_agent"] == "conversation.openai_fallback"


def test_natural_language_ghost_address_is_case_insensitive_and_word_bounded():
    assert assistant_module.is_text_addressed("ah, my bad ghost, forgot about that")
    assert assistant_module.is_text_addressed("GHOST can you help?")
    assert assistant_module.is_text_addressed("hey, Ghost!")
    assert not assistant_module.is_text_addressed("that was ghosted")
    assert not assistant_module.is_text_addressed("ghostly behaviour")


def test_spam_protection_defers_sender_to_configured_local_agent():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.sender_activity = assistant_module.defaultdict(assistant_module.deque)
    assistant.spam_penalties = {}
    assistant.spam_window_seconds = 30
    assistant.spam_message_limit = 3
    assistant.spam_defer_minutes = 10
    assistant.spam_timeout_minutes = 5
    assistant.spam_policy = "defer_local"
    assistant.spam_local_agent = "conversation.local_guard"
    assistant.hass = SimpleNamespace(
        bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None)
    )
    message = SimpleNamespace(guild=None)

    assert assistant._record_spam(message, "123", True) is None
    assert assistant._record_spam(message, "123", True) is None
    assert assistant._record_spam(message, "123", True) == "defer_local"
    assert assistant._record_spam(message, "123", True) == "defer_local"


def test_spam_timeout_policy_drops_messages_during_cooldown():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.sender_activity = assistant_module.defaultdict(assistant_module.deque)
    assistant.spam_penalties = {}
    assistant.spam_window_seconds = 30
    assistant.spam_message_limit = 3
    assistant.spam_defer_minutes = 10
    assistant.spam_timeout_minutes = 5
    assistant.spam_policy = "timeout"
    assistant.spam_local_agent = "conversation.local_guard"
    assistant.hass = SimpleNamespace(
        bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None)
    )
    message = SimpleNamespace(guild=None)

    assistant._record_spam(message, "123", True)
    assistant._record_spam(message, "123", True)
    assert assistant._record_spam(message, "123", True) == "drop"
    assert assistant._record_spam(message, "123", True) == "drop"




def test_group_continuity_overrides_mention_only_for_same_speaker_followup():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = True
    assistant.group_continuity_seconds = 300
    assistant.group_relevance_agent = "conversation.local_relevance"
    assistant.agents = {"conversation_agent": "conversation.api"}
    assistant.limit = 8

    async def unexpected(*args):
        raise AssertionError("A same-speaker follow-up must not call relevance inference")

    assistant._call = unexpected
    history = [
        {
            "role": "user",
            "sender": "Tokyo",
            "sender_id": "123",
            "content": "so what cunt, you fixed yourself yet?",
            "timestamp": "2026-11-14T11:44:00+00:00",
        },
        {
            "role": "assistant",
            "sender": "GHOST",
            "content": "What do you need help with?",
            "timestamp": "2026-11-14T11:45:00+00:00",
        },
    ]
    result = asyncio.run(assistant._should_respond_to_group(
        [{
            "sender_name": "Tokyo",
            "sender_id": "123",
            "content": "you fixed yourself?",
            "timestamp": "2026-11-14T11:45:10+00:00",
            "directly_addressed": False,
        }],
        history,
    ))

    assert result[0] is True
    assert "follow-up" in result[1]


def test_mention_only_still_blocks_unrelated_group_message_without_history():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.mode = "api"
    assistant.group_require_mention = True
    assistant.group_continuity_seconds = 300
    assistant.group_relevance_agent = "conversation.local_relevance"
    assistant.agents = {"conversation_agent": "conversation.api"}
    assistant.limit = 8

    async def unexpected(*args):
        raise AssertionError("Mention-only mode must not call relevance inference")

    assistant._call = unexpected
    result = asyncio.run(assistant._should_respond_to_group(
        [{
            "sender_name": "Tokyo",
            "sender_id": "123",
            "content": "Anyone fancy a game?",
            "timestamp": "2026-11-14T11:45:10+00:00",
            "directly_addressed": False,
        }],
        [],
    ))

    assert result[0] is False
    assert "mention-only" in result[1]



def test_reminder_confirmation_executes_only_a_clear_pending_offer():
    result = assistant_module.resolve_reminder_confirmation(
        [{"content": "yes pall"}],
        [{
            "role": "assistant",
            "content": "You want a reminder in two minutes to text Ryan, right? Confirm if you'd like me to set that up.",
        }],
        datetime(2026, 11, 14, 12, 34, tzinfo=UTC),
    )
    assert result == {"name": "text Ryan", "duration_seconds": 120}


def test_reminder_confirmation_decline_never_creates_reminder():
    result = assistant_module.resolve_reminder_confirmation(
        [{"content": "nah"}],
        [{
            "role": "assistant",
            "content": "You want a reminder in two minutes to text Ryan, right? Confirm if you'd like me to set that up.",
        }],
        datetime(2026, 11, 14, 12, 34, tzinfo=UTC),
    )
    assert result == {"declined": True}


def test_reminder_confirmation_requires_a_real_previous_confirmation_question():
    result = assistant_module.resolve_reminder_confirmation(
        [{"content": "yes"}],
        [{"role": "assistant", "content": "The reminder has not been set."}],
        datetime(2026, 11, 14, 12, 34, tzinfo=UTC),
    )
    assert result is None


def test_reminder_confirmation_does_not_guess_missing_task_details():
    result = assistant_module.resolve_reminder_confirmation(
        [{"content": "yes"}],
        [{
            "role": "assistant",
            "content": "Would you like me to set a two-minute timer now?",
        }],
        datetime(2026, 11, 14, 12, 34, tzinfo=UTC),
    )
    assert result["needs_clarification"] is True


def test_function_configuration_errors_are_non_retryable_and_detected_for_fallback():
    assert assistant_module.is_function_configuration_error(
        "The selected Home Assistant conversation agent could not load its configured functions."
    )
