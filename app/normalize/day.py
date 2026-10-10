from typing import Any

from app.normalize.fit import NormalizeError


def day_metrics(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        raise NormalizeError("Day file is not a JSON object")
    sleep = payload.get("sleep")
    heart = payload.get("heart_rate")
    daily = sleep.get("dailySleepDTO") if isinstance(sleep, dict) else None
    if not isinstance(daily, dict):
        daily = {}
    if not isinstance(heart, dict):
        heart = {}
    found: dict[str, float] = {}
    _put(found, "sleep_duration_sec", daily.get("sleepTimeSeconds"))
    scores = daily.get("sleepScores")
    overall = scores.get("overall") if isinstance(scores, dict) else None
    if isinstance(overall, dict):
        _put(found, "sleep_score", overall.get("value"))
    _put(found, "overnight_hrv", daily.get("avgSleepHRV"))
    _put(found, "resting_hr", heart.get("restingHeartRate"))
    return found


def _put(found: dict[str, float], key: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    found[key] = float(value)
