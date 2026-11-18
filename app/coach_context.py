"""Build the training context a coach model reads.

Everything here comes from tables at request time: the athlete profile, the
imported activity history, the stored daily Garmin metrics, and the scored
wellness rows. Nothing is a constant about one person, and the free-text
wellness note is never read, so it cannot reach a model by accident.

The shape is stable on purpose. The profile sits first because it never changes
between requests, which lets a provider with prompt caching bill that prefix at
the cached rate.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.storage.db import (
    connect,
    ensure_schema,
    load_activity_history,
    load_athlete_profile,
    load_recent_days,
    load_subjective_days,
)

# How far back each part reaches. These are policy, not measurements: enough
# detail to judge today, enough history to see a block and a break.
DETAIL_DAYS = 28
HISTORY_DAYS = 365

# A cap so a long history cannot make the request unbounded. 400 rows is more
# than a year of daily training for one person.
HISTORY_LIMIT = 400


def build_context(today: date | None = None) -> dict[str, Any]:
    """Return the full context, with the profile first for prompt caching."""
    end = today or date.today()
    detail_start = end - timedelta(days=DETAIL_DAYS)
    history_start = end - timedelta(days=HISTORY_DAYS)

    with connect() as connection:
        ensure_schema(connection)
        profile = load_athlete_profile(connection)
        history = load_activity_history(
            connection, history_start.isoformat(), end.isoformat(), HISTORY_LIMIT
        )
        days = load_recent_days(connection, detail_start.isoformat(), end.isoformat())
        wellness = load_subjective_days(connection, detail_start.isoformat(), end.isoformat())

    return {
        "profile": profile or {"notes": None, "avoided_sports": []},
        "today": end.isoformat(),
        "recent_days": days,
        "wellness": wellness,
        "history": history,
    }


def coverage(context: dict[str, Any]) -> dict[str, Any]:
    """Describe what the context actually holds, so a gap is visible, not implied.

    The athlete sees this next to the recommendation: an empty history means the
    import was not run, not that no training happened.
    """
    history = context.get("history") or []
    days = context.get("recent_days") or []
    wellness = context.get("wellness") or []
    return {
        "today": context.get("today"),
        "history_count": len(history),
        "history_first_day": history[0]["day"] if history else None,
        "history_last_day": history[-1]["day"] if history else None,
        "detail_day_count": len(days),
        "wellness_day_count": len(wellness),
        "profile_has_notes": bool((context.get("profile") or {}).get("notes")),
        "avoided_sports": (context.get("profile") or {}).get("avoided_sports") or [],
    }


__all__ = ["DETAIL_DAYS", "HISTORY_DAYS", "HISTORY_LIMIT", "build_context", "coverage"]
