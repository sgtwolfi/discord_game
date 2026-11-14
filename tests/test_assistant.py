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
