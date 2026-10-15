from typing import Any

from app.normalize.fit import NormalizeError


def without_hrv_readings(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    return {key: value for key, value in payload.items() if key != "hrvReadings"}


def day_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NormalizeError("Day file is not a JSON object")
    sleep = payload.get("sleep")
    heart = payload.get("heart_rate")
    daily = sleep.get("dailySleepDTO") if isinstance(sleep, dict) else None
    if not isinstance(daily, dict):
        daily = {}
    if not isinstance(heart, dict):
        heart = {}
    found: dict[str, Any] = {}
    _put_number(found, "sleep_duration_sec", daily.get("sleepTimeSeconds"))
    scores = daily.get("sleepScores")
    overall = scores.get("overall") if isinstance(scores, dict) else None
    if isinstance(overall, dict):
        _put_number(found, "sleep_score", overall.get("value"))
    _put_number(found, "overnight_hrv", daily.get("avgSleepHRV"))
    _put_number(found, "resting_hr", heart.get("restingHeartRate"))
    _put_daily_status(found, payload)
    return found


def _put_daily_status(found: dict[str, Any], payload: dict[str, Any]) -> None:
    hrv = payload.get("hrv")
    summary = hrv.get("hrvSummary") if isinstance(hrv, dict) else None
    if isinstance(summary, dict):
        _put_text(found, "hrv_status", summary.get("status"))

    readiness = _readiness_entry(payload.get("training_readiness"))
    if readiness is not None:
        _put_number(found, "readiness_score", readiness.get("score"))
        _put_text(found, "readiness_level", readiness.get("level"))

    status = _primary_device(payload.get("daily_training_status"), "latestTrainingStatusData")
    if status is not None:
        _put_text(found, "training_status", status.get("trainingStatusFeedbackPhrase"))
        acute = status.get("acuteTrainingLoadDTO")
        if isinstance(acute, dict):
            _put_number(found, "garmin_load_acute", acute.get("dailyTrainingLoadAcute"))
            _put_number(found, "garmin_load_chronic", acute.get("dailyTrainingLoadChronic"))
            _put_number(found, "garmin_acwr", acute.get("dailyAcuteChronicWorkloadRatio"))

    metrics = _max_metrics_entry(payload.get("max_metrics"))
    if metrics is not None:
        _put_vo2(found, "vo2max_generic", metrics.get("generic"))
        _put_vo2(found, "vo2max_cycling", metrics.get("cycling"))

    balance = _primary_device(payload.get("four_week_load_balance"), "metricsTrainingLoadBalanceDTOMap")
    if balance is not None:
        _put_number(found, "monthly_load_aerobic_low", balance.get("monthlyLoadAerobicLow"))
        _put_number(found, "monthly_load_aerobic_high", balance.get("monthlyLoadAerobicHigh"))
        _put_number(found, "monthly_load_anaerobic", balance.get("monthlyLoadAnaerobic"))


def _readiness_entry(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        entries = [payload]
    elif isinstance(payload, list):
        entries = [item for item in payload if isinstance(item, dict)]
    else:
        return None
    primary = [item for item in entries if item.get("primaryActivityTracker") is True]
    pool = primary or entries
    if not pool:
        return None
    return max(pool, key=lambda item: item.get("timestamp") if isinstance(item.get("timestamp"), str) else "")


def _primary_device(payload: Any, map_key: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    records = payload.get(map_key)
    if not isinstance(records, dict):
        return None
    for record in records.values():
        if isinstance(record, dict) and record.get("primaryTrainingDevice") is True:
            return record
    return None


def _max_metrics_entry(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    return None


def _put_vo2(found: dict[str, Any], key: str, block: Any) -> None:
    if not isinstance(block, dict):
        return
    precise = block.get("vo2MaxPreciseValue")
    _put_number(found, key, precise if _is_number(precise) else block.get("vo2MaxValue"))


def _put_number(found: dict[str, Any], key: str, value: Any) -> None:
    if not _is_number(value):
        return
    found[key] = float(value)


def _put_text(found: dict[str, Any], key: str, value: Any) -> None:
    if not isinstance(value, str) or not value:
        return
    found[key] = value


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))
