import hashlib
import json
import os
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
)

from app.garmin.client import GarminNotConfigured
from app.storage.crypto import EncryptionKeyMissing
from app.storage.db import (
    DatabaseNotConfigured,
    connect,
    ensure_schema,
    find_activity_raw_object,
    find_day_raw_object,
    find_raw_object,
    insert_raw_object,
    load_token,
    save_token,
)
from app.storage.blob import put_private


class ArchiveError(Exception):
    """Raised when the latest activity cannot be archived."""


# Newest page Garmin returns in one activities request. The library default is 20.
_RECENT_ACTIVITY_LIMIT = 20


def archive_latest() -> dict[str, Any]:
    key_material = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    if not key_material:
        raise EncryptionKeyMissing

    with connect() as connection:
        ensure_schema(connection)
        saved_token = load_token(connection, key_material)

    client = _login(saved_token)

    with connect() as connection:
        save_token(connection, client.client.dumps(), client.profile_id, key_material)
        activities = client.get_activities(0, _RECENT_ACTIVITY_LIMIT)
        if not isinstance(activities, list):
            raise ArchiveError("No recent activity")
        target = _select_target(connection, activities)

    if target is None:
        raise ArchiveError("No recent activity")

    user_id = client.profile_id if isinstance(client.profile_id, int) else "unknown"
    activity_record = target["activity_record"]
    day_record = target["day_record"]
    if activity_record is None:
        zip_bytes = client.download_activity(
            str(target["activity_id"]),
            dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL,
        )
        if not isinstance(zip_bytes, (bytes, bytearray)):
            raise ArchiveError("Activity download was not bytes")
        with connect() as connection:
            activity_record = _store_bytes(
                connection,
                body=bytes(zip_bytes),
                kind="activity",
                source_format="zip",
                pathname=f"garmin/{user_id}/activity/{target['activity_id']}",
                extension="zip",
                content_type="application/zip",
                garmin_activity_id=target["activity_id"],
                day=None,
            )
    if day_record is None:
        day_body = json.dumps(
            {
                "sleep": client.get_sleep_data(target["day"]),
                "heart_rate": client.get_heart_rates(target["day"]),
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        with connect() as connection:
            day_record = _store_bytes(
                connection,
                body=day_body,
                kind="day",
                source_format="json",
                pathname=f"garmin/{user_id}/day/{target['day']}",
                extension="json",
                content_type="application/json",
                garmin_activity_id=None,
                day=target["day"],
            )

    return {"activity": activity_record, "day": day_record}


def _select_target(connection: Any, activities: list[Any]) -> dict[str, Any] | None:
    fallback = None
    for activity in activities:
        if not isinstance(activity, dict):
            continue
        try:
            activity_id = _activity_id(activity)
            day = _activity_day(activity)
        except ArchiveError:
            continue
        existing_activity = find_activity_raw_object(connection, activity_id)
        existing_day = find_day_raw_object(connection, day)
        target = {
            "activity_id": activity_id,
            "day": day,
            "activity_record": _already_stored(existing_activity),
            "day_record": _already_stored(existing_day),
        }
        if existing_activity is not None and existing_day is not None:
            if fallback is None:
                fallback = target
            continue
        return target
    return fallback


def _already_stored(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    stored = dict(record)
    stored["stored"] = False
    return stored


def _login(saved_token: str | None) -> Garmin:
    email = os.environ.get("GARMIN_EMAIL") or None
    password = os.environ.get("GARMIN_PASSWORD") or None
    if saved_token:
        try:
            client = Garmin(email=email, password=password)
            client.login(saved_token)
            return client
        except GarminConnectAuthenticationError:
            if not (email and password):
                raise
    if not (email and password):
        raise GarminNotConfigured
    client = Garmin(email=email, password=password)
    client.login(None)
    return client


def _store_bytes(
    connection,
    *,
    body: bytes,
    kind: str,
    source_format: str,
    pathname: str,
    extension: str,
    content_type: str,
    garmin_activity_id: int | None,
    day: str | None,
) -> dict[str, Any]:
    sha256 = hashlib.sha256(body).hexdigest()
    existing = find_raw_object(connection, sha256)
    if existing is not None:
        existing["stored"] = False
        return existing
    source_path = put_private(f"{pathname}/{sha256}.{extension}", body, content_type)
    record = insert_raw_object(
        connection,
        {
            "kind": kind,
            "garmin_activity_id": garmin_activity_id,
            "day": day,
            "source_format": source_format,
            "source_path": source_path,
            "source_sha256": sha256,
            "byte_size": len(body),
        },
    )
    record["stored"] = True
    return record


def _activity_id(activity: dict[str, Any]) -> int:
    value = activity.get("activityId")
    if isinstance(value, bool):
        raise ArchiveError("Recent activity has no id")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ArchiveError("Recent activity has no id")


def _activity_day(activity: dict[str, Any]) -> str:
    start = activity.get("startTimeLocal") or activity.get("startTimeGMT")
    if not isinstance(start, str) or len(start) < 10:
        raise ArchiveError("Recent activity has no local date")
    day = start[:10]
    if day[4] != "-" or day[7] != "-":
        raise ArchiveError("Recent activity has no local date")
    return day


__all__ = [
    "ArchiveError",
    "DatabaseNotConfigured",
    "EncryptionKeyMissing",
    "archive_latest",
]
