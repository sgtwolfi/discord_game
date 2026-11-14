"""Focused tests for GHOST context and response handling without a live HA instance."""

import importlib
import sys
import types
from pathlib import Path

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
    assistant.limit = 4
    assistant.budget = 40
    batch = [{
        "sender_name": "Max",
        "content": "x" * 200 + "PLEASE KEEP THIS END",
        "is_dm": True,
    }]
    prompt = assistant._prompt(batch, [], "private contact summary")
    assert "PLEASE KEEP THIS END" in prompt
    assert "private contact summary" in prompt
    assert "You are GHOST" in prompt


def test_prompt_uses_only_supplied_contact_history():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.limit = 10
    assistant.budget = 1000
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
    from datetime import datetime, timezone
    from types import SimpleNamespace
    import asyncio

    assistant = DiscordAssistant.__new__(DiscordAssistant)
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
        created_at=datetime.now(timezone.utc),
    )

    asyncio.run(assistant.enqueue(message, is_dm=True, sender_id="456", sender_name="Max"))

    assert assistant.queue == []


def test_enqueue_applies_backpressure_instead_of_dropping_oldest_message():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    import asyncio

    fired = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
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
        created_at=datetime.now(timezone.utc),
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
    from types import SimpleNamespace
    import asyncio

    events = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
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
                "failed": [{"name": "Hall", "id": "light.hall"}],
            },
        },
    })

    assert snapshot == {
        "response_type": "action_done",
        "success": [{"name": "Bedroom", "id": "light.bedroom"}],
        "failed": [{"name": "Hall", "id": "light.hall"}],
    }



def test_sensor_attributes_expose_paused_state_and_active_request():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.enabled = True
    assistant.paused = True
    assistant.queue = []
    assistant.active = False
    assistant.agents = {"conversation_agent": "conversation.local"}
    assistant.last_activity = None
    assistant.error = None
    assistant.transcript = []
    assistant.active_request = {"conversation": "dm:123"}
    assistant.friends = {}

    attributes = assistant.attributes()

    assert attributes["paused"] is True
    assert attributes["active_request"] == {"conversation": "dm:123"}



def test_queued_message_can_be_edited_and_cancelled_individually():
    from types import SimpleNamespace
    import asyncio

    events = []
    assistant = DiscordAssistant.__new__(DiscordAssistant)
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
    import asyncio
    import pytest

    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.queue = [{"message_id": "111", "content": "original"}]

    with pytest.raises(ValueError, match="cannot be empty"):
        asyncio.run(assistant.edit_queued_message("111", "   "))



def test_transcript_replay_requeues_original_dm_messages():
    from types import SimpleNamespace
    import asyncio

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
