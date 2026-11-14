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
sys.modules.update({
    "homeassistant": ha,
    "homeassistant.components": components,
    "homeassistant.components.sensor": sensor_module,
    "homeassistant.helpers": helpers,
    "homeassistant.helpers.storage": storage_module,
})

repo_root = Path(__file__).resolve().parents[1]
package = types.ModuleType("custom_components.discord_game")
package.__path__ = [str(repo_root / "custom_components" / "discord_game")]
sys.modules["custom_components.discord_game"] = package
assistant_module = importlib.import_module("custom_components.discord_game.assistant")
DiscordAssistant = assistant_module.DiscordAssistant
speech = assistant_module.speech


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
    assistant.queue = []
    assistant.max_queue = 10
    assistant.wake = asyncio.Event()
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda *args, **kwargs: None))
    assistant.sensor = SimpleNamespace(hass=None)
    message = SimpleNamespace(
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
    assistant.queue = [{"content": "earlier message"}]
    assistant.max_queue = 1
    assistant.wake = asyncio.Event()
    assistant.error = None
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(
        async_fire=lambda *args, **kwargs: fired.append((args, kwargs))
    ))
    assistant.sensor = SimpleNamespace(hass=None)
    message = SimpleNamespace(
        content="new message",
        guild=None,
        channel=SimpleNamespace(id=123),
        created_at=datetime.now(UTC),
    )

    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Max"))

    assert assistant.queue == [{"content": "earlier message"}]
    assert "queue is full" in assistant.error
    assert fired and fired[0][0][0] == "discord_game_assistant_error"



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
    assistant.sensor = SimpleNamespace(hass=None)
    assistant.hass = SimpleNamespace(bus=SimpleNamespace(
        async_fire=lambda *args, **kwargs: events.append((args, kwargs))
    ))

    edited = asyncio.run(assistant.edit_queued_message("111", "corrected"))
    assert edited is True
    assert assistant.queue[0]["content"] == "corrected"

    cancelled = asyncio.run(assistant.cancel_queued_message("111"))
    assert cancelled is True
    assert len(assistant.queue) == 1
    assert assistant.queue[0]["message_id"] == "222"
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



def test_memory_compression_keeps_more_raw_history_when_no_memory_agent():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {"123": {
        "summary": "",
        "messages": [{"role": "user", "content": str(i)} for i in range(8)],
    }}
    assistant.limit = 3
    assistant.history_limit = 6
    assistant.agents = {"memory_agent": ""}
    asyncio.run(assistant._compress("123"))

    assert [item["content"] for item in assistant.friends["123"]["messages"]] == ["2", "3", "4", "5", "6", "7"]


def test_memory_compression_keeps_raw_history_when_memory_agent_fails():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {"123": {
        "summary": "existing",
        "messages": [{"role": "user", "content": str(i)} for i in range(8)],
    }}
    assistant.limit = 3
    assistant.history_limit = 6
    assistant.agents = {"memory_agent": "conversation.memory"}
    assistant.budget = 1000

    async def failed_call(agent, prompt):
        raise RuntimeError("model unavailable")

    assistant._call = failed_call
    asyncio.run(assistant._compress("123"))

    assert len(assistant.friends["123"]["messages"]) == 6
    assert assistant.friends["123"]["summary"] == "existing"


def test_memory_compression_trims_to_short_history_after_success():

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.diagnostics_revision = 0
    assistant.friends = {"123": {
        "summary": "",
        "messages": [{"role": "user", "content": str(i)} for i in range(8)],
    }}
    assistant.limit = 3
    assistant.history_limit = 6
    assistant.agents = {"memory_agent": "conversation.memory"}
    assistant.budget = 1000

    async def successful_call(agent, prompt):
        return "durable summary"

    assistant._call = successful_call
    asyncio.run(assistant._compress("123"))

    assert len(assistant.friends["123"]["messages"]) == 3
    assert assistant.friends["123"]["summary"] == "durable summary"



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



def test_fallback_retry_is_allowed_for_missing_action_result():
    assert assistant_module.action_result_retryable({
        "response": {"response_type": "success", "speech": {"plain": {"speech": "Done"}}}
    })


def test_fallback_retry_is_blocked_for_partial_action_failure():
    assert not assistant_module.action_result_retryable({
        "response": {
            "response_type": "action_done",
            "data": {
                "success": [{"id": "light.bedroom"}],
                "failed": [{"id": "light.hall"}],
            },
        },
    })


def test_fallback_retry_is_allowed_when_action_has_no_reported_targets():
    assert assistant_module.action_result_retryable({
        "response": {"response_type": "action_done", "data": {"success": [], "failed": []}}
    })



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
