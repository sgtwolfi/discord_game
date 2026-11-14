"""Deterministic helpers for GHOST Local Mode."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_TRIGGER = re.compile(r"\b(?:remind me|set (?:a )?reminder)\b", re.IGNORECASE)
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}
_DURATION = re.compile(
    r"\bin\s+(?P<amount>\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s*(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b",
    re.IGNORECASE,
)
_CLOCK = re.compile(
    r"\bat\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?\b",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"\b(?P<day>today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(?P<date>20\d{2}-\d{2}-\d{2})\b")
_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def parse_local_reminder(text: str, now: datetime) -> dict | None:
    """Parse only clear reminder requests; return a clarification instead of guessing.

    Supported timing is an explicit relative duration (for example, "in 20
    minutes") or a clock time with an optional date/day (for example,
    "tomorrow at 7pm"). Ambiguous 12-hour times and unsupported date phrases
    are deliberately rejected for clarification.
    """
    value = str(text or "").strip()
    trigger = _TRIGGER.search(value)
    if not trigger:
        return None

    body = value[trigger.end():].strip()
    body = re.sub(r"^(?:to|that)\s+", "", body, flags=re.IGNORECASE)
    duration = _DURATION.search(body)
    clock = _CLOCK.search(body)
    day_match = _DATE.search(body)
    iso_match = _ISO_DATE.search(body)

    if duration and (clock or day_match or iso_match):
        return {"needs_clarification": True, "clarification": "Do you want a countdown or a clock-time reminder? I need one timing method."}

    timing_parts = [match for match in (duration, clock, day_match, iso_match) if match]
    task = body
    for match in sorted(timing_parts, key=lambda item: item.start(), reverse=True):
        task = task[:match.start()] + " " + task[match.end():]
    task = re.sub(r"\b(?:on|at|to)\s*$", "", task, flags=re.IGNORECASE)
    task = re.sub(r"^\s*(?:to|that)\s+", "", task, flags=re.IGNORECASE)
    task = re.sub(r"\s+", " ", task).strip(" ,.!?;:")
    if not task:
        return {"needs_clarification": True, "clarification": "What should I remind you about?"}

    if duration:
        amount_text = duration.group("amount").lower()
        amount = int(amount_text) if amount_text.isdigit() else _NUMBER_WORDS[amount_text]
        unit = duration.group("unit").lower()
        multiplier = 1 if unit.startswith(("second", "sec")) else 60 if unit.startswith(("minute", "min")) else 3600 if unit.startswith(("hour", "hr")) else 86400
        seconds = amount * multiplier
        if seconds < 1 or seconds > 31_536_000:
            return {"needs_clarification": True, "clarification": "That reminder duration is outside the supported range."}
        return {"name": task[:200], "duration_seconds": seconds}

    if not clock:
        return {"needs_clarification": True, "clarification": "When should I remind you? Give me a duration such as 'in 20 minutes' or a time such as 'tomorrow at 7pm'."}

    hour = int(clock.group("hour"))
    minute = int(clock.group("minute") or 0)
    ampm = (clock.group("ampm") or "").lower()
    if minute > 59 or hour > 23 or (ampm and not 1 <= hour <= 12):
        return {"needs_clarification": True, "clarification": "That clock time is invalid. Please give me a valid time."}
    if not ampm and 0 < hour <= 12:
        return {"needs_clarification": True, "clarification": "Is that AM or PM? I don't want to guess the time."}
    if ampm:
        hour = hour % 12
        if ampm == "pm":
            hour += 12
    alarm_time = f"{hour:02d}:{minute:02d}"

    reminder_date = None
    if iso_match:
        try:
            parsed_date = datetime.strptime(iso_match.group("date"), "%Y-%m-%d").date()
        except ValueError:
            return {"needs_clarification": True, "clarification": "That date is invalid. Please give me a real calendar date."}
        if parsed_date < now.date():
            return {"needs_clarification": True, "clarification": "That date is in the past. When should I set it instead?"}
        reminder_date = parsed_date.isoformat()
    elif day_match:
        day = day_match.group("day").lower()
        if day == "today":
            target_date = now.date()
        elif day == "tomorrow":
            target_date = now.date() + timedelta(days=1)
        else:
            days_ahead = (_WEEKDAYS[day] - now.weekday()) % 7
            if days_ahead == 0 or re.search(r"\bnext\s+$", body[:day_match.start()], re.IGNORECASE):
                days_ahead += 7
            target_date = now.date() + timedelta(days=days_ahead)
        reminder_date = target_date.isoformat()

    if reminder_date == now.date().isoformat():
        requested_time = datetime.strptime(alarm_time, "%H:%M").time()
        if requested_time <= now.timetz().replace(tzinfo=None):
            return {"needs_clarification": True, "clarification": "That time has already passed today. Should I set it for tomorrow instead?"}

    return {"name": task[:200], "alarm_time": alarm_time, **({"date": reminder_date} if reminder_date else {})}
