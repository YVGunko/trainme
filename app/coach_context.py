"""Build the training context a coach model reads.

Everything here comes from tables at request time: the athlete profile, the
imported activity history, the stored daily Garmin metrics, and the scored
wellness rows. Nothing is a constant about one person, and the free-text
wellness note is never read, so it cannot reach a model by accident.

A year of raw activities is about 28k tokens. The last fortnight stays raw
because its detail changes the next session; everything older becomes weekly
totals, which carry the shape of the year at a fraction of the size.

The shape is stable on purpose. The profile sits first because it never changes
between requests, which lets a provider with prompt caching bill that prefix at
the cached rate.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.history_summary import RAW_DAYS, split_history, weekly_summary
from app.sports import to_sport
from app.storage.db import (    connect,
    ensure_schema,
    load_activity_history,
    load_athlete_profile,
    load_recent_days,
    load_subjective_days,
)

# How far back each part reaches. These are policy, not measurements: enough
# detail to judge today, enough history to see a block and a break.
# Both ends of the range are inclusive, so the count is DETAIL_DAYS including
# today, not one day more.
DETAIL_DAYS = 28
HISTORY_DAYS = 365

# A cap so a long history cannot make the request unbounded. 400 rows is more
# than a year of daily training for one person.
HISTORY_LIMIT = 400

# The athlete's calendar offset, east of UTC. The same number lives in
# src/lib/training-day.js for the cron; the two must agree, and only the cron
# needs the full precision, so this one is hours.
TRAINING_UTC_OFFSET_MINUTES = 3 * 60

WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)


def build_context(today: date | None = None) -> dict[str, Any]:
    """Return the full context, with the profile first for prompt caching."""
    end = today or date.today()
    # Both ends are inclusive, so counting back DETAIL_DAYS - 1 yields exactly
    # DETAIL_DAYS rows.
    detail_start = end - timedelta(days=DETAIL_DAYS - 1)
    history_start = end - timedelta(days=HISTORY_DAYS)

    with connect() as connection:
        ensure_schema(connection)
        profile = coach_profile(load_athlete_profile(connection), end)
        rows = load_activity_history(
            connection, history_start.isoformat(), end.isoformat(), HISTORY_LIMIT
        )
        days = load_recent_days(connection, detail_start.isoformat(), end.isoformat())
        wellness = load_subjective_days(connection, detail_start.isoformat(), end.isoformat())

    recent, older = split_history(rows, end)
    return {
        "profile": profile,
        "today": end.isoformat(),
        "today_weekday": WEEKDAYS[end.weekday()],
        "timezone": f"UTC+{_offset_hours()}",
        "recent_days": [_day(row) for row in days],
        "wellness": wellness,
        "recent_activities": [_slim(row) for row in recent],
        "weekly_totals": weekly_summary(older),
    }


def coach_profile(raw: dict[str, Any] | None, today: date) -> dict[str, Any]:
    """Shape the stored profile for the model.

    Bookkeeping stays out. Zone sports use the same names as a workout. Age is
    computed for today so the model does not have to count birthdays.
    """
    raw = raw or {}
    birth = raw.get("birth_date")
    return {
        "notes": raw.get("notes"),
        "avoided_sports": list(raw.get("avoided_sports") or []),
        "birth_date": birth,
        "age_years": _age_years(birth, today),
        "weight_kg": raw.get("weight_kg"),
        "height_cm": raw.get("height_cm"),
        "cycling_ftp": raw.get("cycling_ftp"),
        "hr_zones": _zones_for_coach(raw.get("hr_zones")),
        "power_zones": _zones_for_coach(raw.get("power_zones")),
        "recorded_at": raw.get("recorded_at"),
    }


_ZONE_SPORTS = {
    "DEFAULT": "default",
    "RUNNING": "running",
    "CYCLING": "cycling",
    "SWIMMING": "swimming",
    "LAP_SWIMMING": "swimming",
    "STRENGTH_TRAINING": "strength_training",
    "YOGA": "yoga",
    "FITNESS_EQUIPMENT": "fitness_equipment",
}


def _zones_for_coach(zones: Any) -> list[dict[str, Any]]:
    if not isinstance(zones, list):
        return []
    found = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        sport = str(zone.get("sport") or "default")
        item = {
            "sport": _ZONE_SPORTS.get(sport, sport.lower()),
            "floors": list(zone.get("floors") or []),
        }
        if zone.get("ceiling") is not None:
            item["ceiling"] = zone["ceiling"]
        found.append(item)
    return found


def _age_years(birth: Any, today: date) -> int | None:
    if not isinstance(birth, str) or len(birth) < 10:
        return None
    try:
        born = date.fromisoformat(birth[:10])
    except ValueError:
        return None
    years = today.year - born.year
    if (today.month, today.day) < (born.month, born.day):
        years -= 1
    return years if years >= 0 else None


def _offset_hours() -> int:
    # The athlete's calendar, in hours east of UTC. Garmin timestamps arrive
    # already converted, so this only tells the model how to read a clock time.
    return TRAINING_UTC_OFFSET_MINUTES // 60


def coverage(context: dict[str, Any]) -> dict[str, Any]:
    """Describe what the context actually holds, so a gap is visible, not implied.

    The athlete sees this next to the recommendation: an empty history means the
    import was not run, not that no training happened.
    """
    recent = context.get("recent_activities") or []
    weeks = context.get("weekly_totals") or []
    days = context.get("recent_days") or []
    wellness = context.get("wellness") or []
    return {
        "today": context.get("today"),
        "raw_activity_count": len(recent),
        "raw_window_days": RAW_DAYS,
        "week_count": len(weeks),
        "weeks_first": weeks[0]["week"] if weeks else None,
        "weeks_last": weeks[-1]["week"] if weeks else None,
        "detail_day_count": len(days),
        "wellness_day_count": len(wellness),
        "profile_has_notes": bool((context.get("profile") or {}).get("notes")),
        "avoided_sports": (context.get("profile") or {}).get("avoided_sports") or [],
    }


def _day(row: dict[str, Any]) -> dict[str, Any]:
    """Rename the Garmin daily load so it cannot be mistaken for activity load.

    Garmin reports two different numbers that both look like "load": the daily
    training load on a day's metrics, and the training load of one activity in
    the activity list. They use different scales, so a model given both under
    the same name would add or compare them.
    """
    if "garmin_load_acute" not in row:
        return dict(row)
    renamed = {key: value for key, value in row.items() if key != "garmin_load_acute"}
    renamed["garmin_daily_load"] = row["garmin_load_acute"]
    return renamed


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the fields that matter per session, rounded to something readable.

    The sport is folded to the five names a workout can be built for. Garmin's
    own name travels as ``garmin_sport`` so nothing is lost, and ``sport`` is
    always one of the five or "other".

    The athlete's own rating and comment travel with the session: a session that
    felt hard at low power says something the numbers alone do not.
    """
    garmin_sport = row.get("sport")
    slim = {
        "day": row.get("day"),
        "sport": to_sport(garmin_sport),
        "garmin_sport": garmin_sport,
        "minutes": _round(row.get("duration_sec"), 60),
        "km": _round(row.get("distance_m"), 1000),
        "avg_hr": _round(row.get("avg_hr"), 1),
        "activity_load": _round(row.get("training_load"), 1),
    }
    effort = row.get("perceived_effort")
    if effort is not None:
        slim["perceived_effort"] = effort
    feel = row.get("feel")
    if feel is not None:
        slim["feel"] = feel
    note = row.get("activity_note")
    if isinstance(note, str) and note.strip():
        slim["note"] = note.strip()
    return slim


def _round(value: Any, divisor: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value) / divisor, 1)


__all__ = ["DETAIL_DAYS", "HISTORY_DAYS", "HISTORY_LIMIT", "build_context", "coverage"]

