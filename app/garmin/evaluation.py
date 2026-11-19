"""Read the athlete's own verdict on a finished activity.

Garmin keeps two fields the activity list does not return, so each one costs an
extra request per activity:

- ``summaryDTO.directWorkoutRpe``   perceived effort, stored 10-100 for 1-10
- ``summaryDTO.directWorkoutFeel``  "how did you feel", one of 0/25/50/75/100

Both are optional: an athlete may not have rated a session, and older activities
predate the feature. A missing value stays missing rather than becoming a zero,
because a zero effort reading would read as a very easy session.
"""

from __future__ import annotations

from typing import Any

# 0 is "very weak" and 100 is "very strong" in Garmin's own scale.
FEEL_VALUES = (0, 25, 50, 75, 100)


def read_evaluation(activity: Any) -> dict[str, Any]:
    """Return perceived effort, feel, and note from one activity response."""
    summary = activity.get("summaryDTO") if isinstance(activity, dict) else None
    if not isinstance(summary, dict):
        summary = {}
    return {
        "perceived_effort": _effort(summary.get("directWorkoutRpe")),
        "feel": _feel(summary.get("directWorkoutFeel")),
        "activity_note": _note(activity if isinstance(activity, dict) else {}),
    }


def _effort(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    # Garmin stores the 1-10 the athlete entered, multiplied by ten.
    effort = round(number / 10)
    if 1 <= effort <= 10:
        return effort
    return None


def _feel(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return int(number) if int(number) in FEEL_VALUES else None


def _note(activity: dict[str, Any]) -> str | None:
    # The activity summary can carry the athlete's description at either level.
    for source in (activity, activity.get("summaryDTO")):
        if not isinstance(source, dict):
            continue
        text = source.get("description")
        if isinstance(text, str) and text.strip():
            return text.strip()[:4000]
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


__all__ = ["FEEL_VALUES", "read_evaluation"]
