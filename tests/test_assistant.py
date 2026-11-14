"""Focused tests for the GHOST assistant's context and response handling."""

from types import SimpleNamespace

from custom_components.discord_game.assistant import DiscordAssistant, speech


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


def test_prompt_does_not_include_unrelated_contact_history():
    assistant = DiscordAssistant.__new__(DiscordAssistant)
    assistant.limit = 10
    assistant.budget = 1000
    batch = [{"sender_name": "Ryan", "content": "Hello", "is_dm": True}]
    prompt = assistant._prompt(batch, [{"role": "user", "content": "Ryan's own history"}], "")
    assert "Ryan's own history" in prompt
    assert "Max's private history" not in prompt
