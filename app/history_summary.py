"""Turn a year of activity rows into something a model can use.

A year of raw rows is about 28k tokens and most of it is noise: a model does not
need every ride to see that load rose through spring and dropped after an injury.
Weekly totals carry the shape; the last fortnight stays raw because that is where
detail changes the next session.

Everything here is a pure function of the rows, so the numbers can be checked
without a database.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

# Days that stay as individual activities. Inside this window the exact order and
# the exact load of one session matter for tomorrow's plan.
RAW_DAYS = 14


def week_start(day: str) -> str:
    """Return the Monday of the ISO week containing ``day``."""
    parsed = date.fromisoformat(day)
    return (parsed - timedelta(days=parsed.weekday())).isoformat()


def split_history(
    rows: list[dict[str, Any]],
    today: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split rows into the raw recent window and the older rows to summarise."""
    cutoff = today - timedelta(days=RAW_DAYS)
    recent: list[dict[str, Any]] = []
    older: list[dict[str, Any]] = []
    for row in rows:
        try:
            day = date.fromisoformat(str(row.get("day")))
        except (TypeError, ValueError):
            continue
        (recent if day >= cutoff else older).append(row)
    return recent, older


def weekly_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one row per ISO week, oldest first.

    Only totals a coach acts on are kept. Per-sport minutes and a session count
    say how the week was built; the summed load says how hard it was.
    """
    weeks: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = row.get("day")
        if not isinstance(day, str):
            continue
        try:
            key = week_start(day)
        except ValueError:
            continue
        minutes = _minutes(row.get("duration_sec"))
        week = weeks.setdefault(
            key,
            {"week": key, "sessions": 0, "minutes": 0.0, "load": 0.0, "by_sport": {}},
        )
        week["sessions"] += 1
        week["minutes"] += minutes
        week["load"] += _number(row.get("training_load")) or 0.0
        sport = row.get("sport")
        name = sport if isinstance(sport, str) and sport else "other"
        week["by_sport"][name] = week["by_sport"].get(name, 0.0) + minutes

    summary: list[dict[str, Any]] = []
    for key in sorted(weeks):
        week = weeks[key]
        summary.append(
            {
                "week": week["week"],
                "sessions": week["sessions"],
                "minutes": round(week["minutes"], 1),
                "load": round(week["load"], 1),
                "by_sport_minutes": {name: round(value, 1) for name, value in week["by_sport"].items()},
            }
        )
    return summary


def _minutes(seconds: Any) -> float:
    value = _number(seconds)
    return 0.0 if value is None else value / 60.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


__all__ = ["RAW_DAYS", "split_history", "week_start", "weekly_summary"]
