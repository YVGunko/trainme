"""Read Garmin methods the archive does not call.

Nothing is inserted into activity or daily_metrics. After login the refreshed
auth token is stored the same way the archive stores it. Token JSON is never
returned.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Callable

from garminconnect import GarminConnectAuthenticationError

from app.garmin.archive import _login
from app.garmin.client import GarminNotConfigured
from app.storage.crypto import EncryptionKeyMissing
from app.storage.db import DatabaseNotConfigured, connect, load_token, save_token

_SECRET_PARTS = (
    "token",
    "password",
    "secret",
    "cookie",
    "authorization",
    "oauth",
    "bearer",
)


def probe_unused(day: date) -> dict[str, Any]:
    logging.getLogger("garminconnect").setLevel(logging.ERROR)
    client = _open_client()
    iso = day.isoformat()
    report: dict[str, Any] = {"date": iso, "activities": [], "daily": {}}
    activities = _call("activities", lambda: client.get_activities_by_date(iso, iso))
    report["activity_list"] = activities
    if activities["ok"] and isinstance(activities["payload"], list):
        for activity in activities["payload"]:
            if isinstance(activity, dict):
                report["activities"].append(_activity_entry(client, activity))
    report["daily"] = {
        "hrv": _call("hrv", lambda: client.get_hrv_data(iso)),
        "training_readiness": _call("training_readiness", lambda: client.get_training_readiness(iso)),
        "daily_training_status": _call(
            "daily_training_status",
            lambda: client.get_daily_training_status(iso),
        ),
        "max_metrics": _call("max_metrics", lambda: client.get_max_metrics(iso)),
        "four_week_load_balance": _call(
            "four_week_load_balance",
            lambda: client.get_training_four_week_load_balance(iso),
        ),
        "running_tolerance": _call(
            "running_tolerance",
            lambda: client.get_running_tolerance(iso, iso, "daily"),
        ),
    }
    return _redact(report)


def probe_complete(report: dict[str, Any]) -> bool:
    if not report.get("activity_list", {}).get("ok"):
        return False
    for entry in report.get("activities", []):
        if not entry.get("hr_time_in_zones", {}).get("ok"):
            return False
    return all(item.get("ok") for item in report.get("daily", {}).values())


def _open_client() -> Any:
    if not os.environ.get("DATABASE_URL") and os.environ.get("tm_DATABASE_URL"):
        os.environ["DATABASE_URL"] = os.environ["tm_DATABASE_URL"]
    if not os.environ.get("DATABASE_URL"):
        raise DatabaseNotConfigured("DATABASE_URL is not set")
    key_material = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    if not key_material:
        raise EncryptionKeyMissing("TOKEN_ENCRYPTION_KEY is not set")
    with connect() as connection:
        saved_token = load_token(connection, key_material)
    client = _login(saved_token)
    profile_id = client.profile_id if isinstance(client.profile_id, int) else None
    with connect() as connection:
        save_token(connection, client.client.dumps(), profile_id, key_material)
    return client


def _activity_entry(client: Any, activity: dict[str, Any]) -> dict[str, Any]:
    activity_id = activity.get("activityId")
    entry: dict[str, Any] = {
        "activityId": activity_id,
        "activityName": activity.get("activityName"),
        "activityType": activity.get("activityType"),
        "startTimeLocal": activity.get("startTimeLocal"),
    }
    if isinstance(activity_id, int) or (isinstance(activity_id, str) and activity_id.isdigit()):
        entry["hr_time_in_zones"] = _call(
            "hr_time_in_zones",
            lambda activity_id=str(activity_id): client.get_activity_hr_in_timezones(activity_id),
        )
    else:
        entry["hr_time_in_zones"] = {
            "ok": False,
            "error": "MissingActivityId",
            "message": "Activity list row had no numeric activityId",
        }
    return entry


def _call(name: str, fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "payload": fn()}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "message": _safe_text(exc), "method": name}


def _redact(value: Any, key: str = "") -> Any:
    if key and any(part in key.lower() for part in _SECRET_PARTS):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _safe_text(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    if "{" in text and any(part in text.lower() for part in _SECRET_PARTS):
        return type(exc).__name__
    return text[:400]


__all__ = [
    "DatabaseNotConfigured",
    "EncryptionKeyMissing",
    "GarminConnectAuthenticationError",
    "GarminNotConfigured",
    "probe_complete",
    "probe_unused",
]
