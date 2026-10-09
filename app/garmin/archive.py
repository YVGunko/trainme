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
    find_raw_object,
    insert_raw_object,
    load_token,
    save_token,
)
from app.storage.blob import put_private


class ArchiveError(Exception):
    """Raised when the latest activity cannot be archived."""


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

    activities = client.get_activities(0, 1)
    if not isinstance(activities, list) or not activities or not isinstance(activities[0], dict):
        raise ArchiveError("No recent activity")
    activity = activities[0]
    activity_id = _activity_id(activity)
    day = _activity_day(activity)
    user_id = client.profile_id if isinstance(client.profile_id, int) else "unknown"

    zip_bytes = client.download_activity(
        str(activity_id),
        dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL,
    )
    if not isinstance(zip_bytes, (bytes, bytearray)):
        raise ArchiveError("Activity download was not bytes")

    day_body = json.dumps(
        {
            "sleep": client.get_sleep_data(day),
            "heart_rate": client.get_heart_rates(day),
        },
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()

    with connect() as connection:
        activity_record = _store_bytes(
            connection,
            body=bytes(zip_bytes),
            kind="activity",
            source_format="zip",
            pathname=f"garmin/{user_id}/activity/{activity_id}",
            extension="zip",
            content_type="application/zip",
            garmin_activity_id=activity_id,
            day=None,
        )
        day_record = _store_bytes(
            connection,
            body=day_body,
            kind="day",
            source_format="json",
            pathname=f"garmin/{user_id}/day/{day}",
            extension="json",
            content_type="application/json",
            garmin_activity_id=None,
            day=day,
        )

    return {"activity": activity_record, "day": day_record}


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
