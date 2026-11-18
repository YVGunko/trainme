"""Read and write the athlete profile, and read training history for the coach."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from app.profile import parse_profile
from app.storage.crypto import EncryptionKeyMissing
from app.storage.db import (
    DatabaseNotConfigured,
    connect,
    ensure_schema,
    load_activity_history,
    load_athlete_profile,
    save_athlete_profile,
)

# How much history a recommendation reads: enough to see a training block and a
# break, not so much that the prompt carries a decade of noise.
HISTORY_DAYS = 365
HISTORY_LIMIT = 300


def read_profile() -> dict[str, Any]:
    with connect() as connection:
        ensure_schema(connection)
        found = load_athlete_profile(connection)
    return found or {"notes": None, "avoided_sports": []}


def write_profile(body: Any) -> dict[str, Any]:
    profile = parse_profile(body)
    with connect() as connection:
        ensure_schema(connection)
        return save_athlete_profile(connection, profile["notes"], profile["avoided_sports"])


def read_training_history(today: date | None = None) -> dict[str, Any]:
    """Return stored activity summaries for the last year.

    The history is only what import_history stored. Missing rows mean the
    athlete did not import that period, not that nothing was done, so the caller
    must not read an empty history as "no training".
    """
    end = today or date.today()
    start = end - timedelta(days=HISTORY_DAYS)
    with connect() as connection:
        ensure_schema(connection)
        rows = load_activity_history(
            connection, start.isoformat(), end.isoformat(), HISTORY_LIMIT
        )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "activity_count": len(rows),
        "activities": rows,
    }


__all__ = [
    "HISTORY_DAYS",
    "HISTORY_LIMIT",
    "EncryptionKeyMissing",
    "DatabaseNotConfigured",
    "read_profile",
    "read_training_history",
    "write_profile",
]
