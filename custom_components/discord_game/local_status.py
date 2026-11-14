"""Deterministic read-only Home Assistant lookups for GHOST Local Mode."""

from __future__ import annotations

import difflib
import re
from datetime import datetime

_PERSON_ACTIVITY = re.compile(
    r"\b(?:what(?:'s|s| is)|tell me what)\s+(.+?)\s+(?:doing|up to)\b",
    re.IGNORECASE,
)
_TIME_QUERY = re.compile(r"\b(?:current time|what time is it|what's the time|whats the time|time right now)\b", re.IGNORECASE)
_WEATHER_QUERY = re.compile(r"\b(?:weather|forecast|temperature outside|how warm is it outside)\b", re.IGNORECASE)
_LIGHT_QUERY = re.compile(r"\b(?:light|lights|lamp|lamps)\b", re.IGNORECASE)
_STATUS_QUERY = re.compile(
    r"\b(?:what(?:'s|s| is)\s+my\s+(?:current\s+)?status|"
    r"what am i\s+(?:currently\s+)?(?:doing|up to)|"
    r"how am i getting on|my status|my current activity)\b",
    re.IGNORECASE,
)


def _name(state) -> str:
    return str(state.attributes.get("friendly_name") or state.entity_id)


def _person_activity(hass, requested_name: str) -> str:
    wanted = requested_name.strip(" ?!.,'\"").casefold()
    wanted = re.sub(r"['’]s$", "", wanted)
    if not wanted:
        return "I couldn't identify whose Discord activity you wanted."
    candidates = []
    ranked = []
    for state in hass.states.async_all():
        if not state.entity_id.startswith("sensor.discord_user_"):
            continue
        attrs = state.attributes
        names = {
            _name(state).casefold(),
            str(attrs.get("display_name") or "").casefold(),
            str(attrs.get("user_name") or "").casefold(),
        }
        names.discard("")
        if wanted in names:
            candidates.append(state)
        else:
            score = max(difflib.SequenceMatcher(None, wanted, name).ratio() for name in names)
            ranked.append((score, state))
    if not candidates and ranked:
        ranked.sort(key=lambda item: item[0], reverse=True)
        best_score, best_state = ranked[0]
        next_score = ranked[1][0] if len(ranked) > 1 else 0
        if best_score >= 0.72 and best_score - next_score >= 0.08:
            candidates.append(best_state)
    if not candidates:
        return f"I can't see a clear Discord activity match for {requested_name.strip()}."

    state = candidates[0]
    attrs = state.attributes
    activities = [
        ("game", "playing"),
        ("listening", "listening to"),
        ("streaming", "streaming"),
        ("watching", "watching"),
        ("custom_status", "has the status"),
    ]
    for key, verb in activities:
        activity = attrs.get(key)
        if activity:
            return f"{_name(state)} is {verb} {activity}."
    voice = attrs.get("voice_channel")
    if voice:
        return f"{_name(state)} is in the {voice} voice channel."
    presence = str(state.state or "").lower()
    if presence in {"online", "idle", "dnd", "offline"}:
        return f"{_name(state)} is {presence}, but Discord isn't reporting an activity."
    return f"I found {_name(state)}, but its current Discord activity isn't available."


def _weather(hass) -> str:
    entities = [state for state in hass.states.async_all() if state.entity_id.startswith("weather.")]
    if not entities:
        return "I can't see a Home Assistant weather entity, so I can't give you current conditions."
    state = entities[0]
    attrs = state.attributes
    details = [str(attrs.get("temperature")) + str(attrs.get("temperature_unit") or "°") if attrs.get("temperature") is not None else ""]
    if attrs.get("humidity") is not None:
        details.append("humidity " + str(attrs["humidity"]) + "%")
    if attrs.get("wind_speed") is not None:
        details.append("wind " + str(attrs["wind_speed"]) + str(attrs.get("wind_speed_unit") or ""))
    details = [item for item in details if item]
    condition = str(state.state or "unknown").replace("_", " ")
    suffix = " (" + ", ".join(details) + ")" if details else ""
    return f"{_name(state)} reports {condition}{suffix}."


def _lights(hass, query: str) -> str:
    entities = [state for state in hass.states.async_all() if state.entity_id.startswith("light.")]
    room_terms = [
        word for word in re.findall(r"[a-z0-9]+", query.lower())
        if word not in {"what", "whats", "is", "are", "the", "current", "status", "state", "of", "set", "to", "light", "lights", "lamp", "lamps", "doing", "right", "now"}
    ]
    if room_terms:
        matching = [
            state for state in entities
            if any(term in (_name(state) + " " + state.entity_id).casefold() for term in room_terms)
        ]
        if matching:
            entities = matching
    if not entities:
        return "I can't find any Home Assistant light entities to check."
    readings = []
    for state in entities[:6]:
        description = _name(state) + " is " + str(state.state)
        brightness = state.attributes.get("brightness")
        if brightness is not None:
            description += f" at {round(float(brightness) / 255 * 100)} percent brightness"
        readings.append(description)
    extra = f" And {len(entities) - 6} more." if len(entities) > 6 else ""
    return "; ".join(readings) + "." + extra


def _is_owner_activity_query(query: str, owner_name: str) -> bool:
    """Match the configured owner's name, including possessive phrasing."""
    name = re.escape(str(owner_name or "Harvey").strip() or "Harvey")
    return bool(re.search(
        rf"\bwhat(?:'s|s| is)\s+(?:{name}|the owner)(?:['’]s)?\s+"
        r"(?:currently\s+)?(?:doing|up to|current status|status)\b",
        query,
        re.IGNORECASE,
    ))


def _owner_status(hass, status_entity: str, owner_name: str) -> str:
    """Read the configured owner's live status directly from Home Assistant."""
    states = getattr(hass, "states", None)
    state = states.get(status_entity) if states is not None and hasattr(states, "get") else None
    name = str(owner_name or "Harvey").strip() or "Harvey"
    if state is None or str(state.state).strip().lower() in {"", "unknown", "unavailable", "none"}:
        return f"I can't read {name}'s current status because {status_entity} is unavailable."
    return f"{name} is currently: {str(state.state).strip()[:1000]}"


def answer_local_status(
    hass,
    query: str,
    now: datetime,
    status_entity: str = "input_text.ghost_status",
    owner_name: str = "Harvey",
) -> str | None:
    """Answer simple live-state questions from HA state, without an LLM tool call."""
    value = str(query or "").strip()
    owner = str(owner_name or "Harvey").strip() or "Harvey"
    person = _PERSON_ACTIVITY.search(value)
    if _STATUS_QUERY.search(value) or _is_owner_activity_query(value, owner):
        return _owner_status(hass, status_entity, owner)
    if person:
        requested = re.sub(r"['’]s$", "", person.group(1).strip()).casefold()
        if (
            requested in {owner.casefold(), "the owner", "me", "myself", "i"}
            or difflib.SequenceMatcher(None, requested, owner.casefold()).ratio() >= 0.82
        ):
            return _owner_status(hass, status_entity, owner)
    parts = []
    if person:
        person_answer = _person_activity(hass, person.group(1))
        if "can't see a clear Discord activity match" not in person_answer and "can't see a Discord activity sensor" not in person_answer:
            return person_answer
        if not (_TIME_QUERY.search(value) or _WEATHER_QUERY.search(value)):
            return person_answer
        parts.append(person_answer)
    if _TIME_QUERY.search(value):
        parts.append("It's " + now.strftime("%A %H:%M") + ".")
    if _WEATHER_QUERY.search(value):
        parts.append(_weather(hass))
    if parts:
        return " ".join(parts)
    if _LIGHT_QUERY.search(value):
        return _lights(hass, value)
    return None
