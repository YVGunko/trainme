import os
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

class GarminNotConfigured(Exception):
    """Raised when neither saved tokens nor a username and password are set."""


def fetch_recent_activities(limit: int) -> list[dict[str, Any]]:
    tokenstore = os.environ.get("GARMINTOKENS") or os.environ.get("GARMIN_TOKENSTORE") or None
    email = os.environ.get("GARMIN_EMAIL") or None
    password = os.environ.get("GARMIN_PASSWORD") or None
    if not tokenstore and not (email and password):
        raise GarminNotConfigured

    client = Garmin(email=email, password=password)
    client.login(tokenstore)
    activities = client.get_activities(0, limit)
    if not isinstance(activities, list):
        raise GarminConnectConnectionError("Activity list was not a list")
    return [summarize_activity(item) for item in activities if isinstance(item, dict)]


def summarize_activity(activity: dict[str, Any]) -> dict[str, Any]:
    activity_type = activity.get("activityType")
    sport = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
    return {
        "garmin_activity_id": activity.get("activityId"),
        "name": activity.get("activityName"),
        "sport": sport,
        "start": activity.get("startTimeLocal") or activity.get("startTimeGMT"),
        "duration_sec": _number(activity.get("duration")),
        "distance_m": _number(activity.get("distance")),
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


__all__ = [
    "GarminConnectAuthenticationError",
    "GarminConnectConnectionError",
    "GarminConnectTooManyRequestsError",
    "GarminNotConfigured",
    "fetch_recent_activities",
    "summarize_activity",
]
