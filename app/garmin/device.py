"""Choose a Garmin device for a workout and push the workout to it.

Everything here takes an already signed-in ``Garmin`` client, so one login
serves the whole request the same way the archive does.

A cycling or running workout goes to the device that last recorded an activity
of that sport, so a bike workout ends up on the bike computer and a run on the
watch. Other sports, and the case of a sport with no recorded activity, use the
primary training device and then the last used device.
"""

from __future__ import annotations

from typing import Any

from garminconnect import (
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

# The activity type filter this library version documents for get_activities.
_SPORT_ACTIVITY_TYPES = {"cycling": "cycling", "running": "running"}

# How many recent activities decide the device for a sport. One page is enough
# to find the last ride or run when the account alternates sports.
_RECENT_ACTIVITY_LIMIT = 20

# push_workout_to_device is not wrapped in the library's error translation, so
# a rate limit reaches us as a connection error that starts with the status.
# Recheck this if the pinned library version changes.
_RATE_LIMIT_PREFIX = "API Error 429"


class WorkoutDeviceError(Exception):
    """Raised when no registered device can take the workout."""


class WorkoutRateLimited(Exception):
    """Raised when Garmin rate-limits the device message call."""


class WorkoutNotPushed(Exception):
    """Raised when the workout exists in Garmin but did not reach the device."""

    def __init__(self, workout_id: int, device_id: int | None) -> None:
        self.workout_id = workout_id
        self.device_id = device_id
        super().__init__("Workout was uploaded but not pushed to the device")


def list_devices(client: Any) -> dict[str, Any]:
    """Return the registered devices and the primary training device id."""
    devices = client.get_devices()
    if not isinstance(devices, list):
        raise WorkoutDeviceError("Garmin device list was not a list")
    primary = primary_device_id(client)
    return {
        "devices": [_device(device, primary) for device in devices if isinstance(device, dict)],
        "primary_device_id": primary,
    }


def resolve_device(client: Any, sport: str, device_id: int | None = None) -> dict[str, Any]:
    """Return the device a workout of this sport should be pushed to."""
    if device_id is not None:
        return {"device_id": device_id, "source": "requested"}
    found = sport_device_id(client, sport)
    if found is not None:
        return {"device_id": found, "source": "sport"}
    found = primary_device_id(client)
    if found is not None:
        return {"device_id": found, "source": "primary"}
    found = last_used_device_id(client)
    if found is not None:
        return {"device_id": found, "source": "last_used"}
    raise WorkoutDeviceError("No Garmin device is registered for this account")


def sport_device_id(client: Any, sport: str) -> int | None:
    """Return the device that last recorded an activity of this sport."""
    activity_type = _SPORT_ACTIVITY_TYPES.get(sport)
    if activity_type is None:
        return None
    activities = client.get_activities(0, _RECENT_ACTIVITY_LIMIT, activitytype=activity_type)
    if not isinstance(activities, list):
        return None
    for activity in activities:
        if not isinstance(activity, dict):
            continue
        found = parse_device_id(activity.get("deviceId"))
        if found is not None:
            return found
    return None


def primary_device_id(client: Any) -> int | None:
    """Return the primary training device id, or None when Garmin has none."""
    try:
        report = client.get_primary_training_device()
    except GarminConnectConnectionError:
        # The web gateway answers 404 when the account has no primary device.
        return None
    if not isinstance(report, dict):
        return None
    primary = report.get("PrimaryTrainingDevice")
    if not isinstance(primary, dict):
        return None
    return parse_device_id(primary.get("deviceId"))


def last_used_device_id(client: Any) -> int | None:
    """Return the last used device id, or None when Garmin has none."""
    try:
        report = client.get_device_last_used()
    except GarminConnectConnectionError:
        return None
    if not isinstance(report, dict):
        return None
    return parse_device_id(report.get("userDeviceId"))


def push_workout(client: Any, workout_id: int, device_id: int) -> dict[str, Any]:
    """Send one uploaded workout to one device."""
    try:
        client.push_workout_to_device(workout_id, device_id)
    except GarminConnectConnectionError as error:
        if str(error).startswith(_RATE_LIMIT_PREFIX):
            raise WorkoutRateLimited(str(error)[:200]) from error
        raise WorkoutNotPushed(workout_id, device_id) from error
    except GarminConnectTooManyRequestsError as error:
        raise WorkoutRateLimited(str(error)[:200]) from error
    return {"device_id": device_id, "pushed": True}


def parse_device_id(value: Any) -> int | None:
    """Read a device id from a request body or a Garmin record."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or value <= 0:
        return None
    return value


def _device(device: dict[str, Any], primary: int | None) -> dict[str, Any]:
    device_id = parse_device_id(device.get("deviceId"))
    categories = device.get("deviceCategories")
    return {
        "device_id": device_id,
        "name": device.get("displayName") or device.get("productDisplayName"),
        "primary": device_id is not None and device_id == primary,
        "categories": [item for item in categories if isinstance(item, str)]
        if isinstance(categories, list)
        else [],
    }


__all__ = [
    "WorkoutDeviceError",
    "WorkoutNotPushed",
    "WorkoutRateLimited",
    "last_used_device_id",
    "list_devices",
    "parse_device_id",
    "primary_device_id",
    "push_workout",
    "resolve_device",
    "sport_device_id",
]
