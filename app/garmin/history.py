"""Read the Garmin activity list for a period and store the summaries.

This is deliberately not the archive. No FIT file is downloaded and no daily
metric is read, so a year costs a handful of paginated requests instead of the
thousands that archiving a year of days would need. The rows land in
activity_history and are what the coach reads as training history.

A FIT file still holds what the activity screen parses. This path only answers
"what did I do", not "what exactly happened inside it".
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

from app.garmin.archive import (
    ArchiveError,
    _activity_day,
    _activity_id,
    _activity_start,
    _login,
)
from app.garmin.client import GarminNotConfigured
from app.storage.crypto import EncryptionKeyMissing
from app.storage.db import (
    DatabaseNotConfigured,
    activity_history_count,
    connect,
    ensure_schema,
    load_token,
    save_token,
    upsert_activity_history,
)

logger = logging.getLogger(__name__)

# A year of activities is a few hundred rows. The guard is for a mistyped date
# that would otherwise ask Garmin for a decade in one request.
_MAX_HISTORY_DAYS = 400


class HistoryPeriodError(Exception):
    """Raised when a history period is not acceptable."""


def import_history(start: str, end: str) -> dict[str, Any]:
    """Read activity summaries between two dates and store them."""
    start_date, end_date = parse_history_period(start, end)
    key_material = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    if not key_material:
        raise EncryptionKeyMissing

    with connect() as connection:
        ensure_schema(connection)
        saved_token = load_token(connection, key_material)

    client = _login(saved_token)
    with connect() as connection:
        save_token(connection, client.client.dumps(), client.profile_id, key_material)

    activities = client.get_activities_by_date(
        start_date.isoformat(), end_date.isoformat(), sortorder="asc"
    )
    if not isinstance(activities, list):
        raise ArchiveError("Activity list was not a list")

    rows: list[dict[str, Any]] = []
    skipped = 0
    for activity in activities:
        if not isinstance(activity, dict):
            skipped += 1
            continue
        try:
            rows.append(_history_row(activity))
        except ArchiveError:
            skipped += 1
            continue

    with connect() as connection:
        stored = upsert_activity_history(connection, rows)
        total = activity_history_count(connection)

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "activity_count": len(activities),
        "stored_count": stored,
        "skipped_count": skipped,
        "history_total": total,
    }


def parse_history_period(start: str, end: str) -> tuple[date, date]:
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError) as error:
        raise HistoryPeriodError("Period dates must be YYYY-MM-DD") from error
    if end_date < start_date:
        raise HistoryPeriodError("Period end is before start")
    if (end_date - start_date).days + 1 > _MAX_HISTORY_DAYS:
        raise HistoryPeriodError("Period is longer than 400 days")
    return start_date, end_date


def _history_row(activity: dict[str, Any]) -> dict[str, Any]:
    """Take only what a training history needs, and fail when the date is missing."""
    day = _activity_day(activity)
    start_local = _activity_start(activity)
    if start_local is None:
        raise ArchiveError("Activity has no local start")
    activity_type = activity.get("activityType")
    sport = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
    return {
        "garmin_activity_id": _activity_id(activity),
        "start_local": start_local,
        "day": day,
        "sport": sport if isinstance(sport, str) else None,
        "duration_sec": _number(activity.get("duration")),
        "distance_m": _number(activity.get("distance")),
        "avg_hr": _number(activity.get("averageHR")),
        "max_hr": _number(activity.get("maxHR")),
        "calories": _number(activity.get("calories")),
        "training_load": _number(activity.get("activityTrainingLoad")),
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


__all__ = [
    "DatabaseNotConfigured",
    "EncryptionKeyMissing",
    "GarminNotConfigured",
    "HistoryPeriodError",
    "import_history",
    "parse_history_period",
]
