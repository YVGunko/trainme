import hashlib
import json
import logging
import os
from datetime import date, timedelta
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from app.garmin.client import GarminNotConfigured
from app.normalize.day import day_metrics, without_hrv_readings
from app.normalize.store import write_day_metrics
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
    stored_days,
    save_hr_zone_seconds,
    save_power_zone_seconds,
    upsert_activity_meta,
)
from app.storage.blob import get_private, put_private

logger = logging.getLogger(__name__)


class ArchiveError(Exception):
    """Raised when the latest activity cannot be archived."""


class PeriodError(ArchiveError):
    """Raised when a requested archive period is not acceptable."""


# Newest page Garmin returns in one activities request. The library default is 20.
_RECENT_ACTIVITY_LIMIT = 20
_MAX_PERIOD_DAYS = 14


def refresh_stored_days() -> dict[str, Any]:
    """Re-read daily Garmin metrics for each day already stored in Postgres."""
    logging.getLogger("garminconnect").setLevel(logging.ERROR)
    key_material = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    if not key_material:
        raise EncryptionKeyMissing
    with connect() as connection:
        ensure_schema(connection)
        saved_token = load_token(connection, key_material)
        days = stored_days(connection)
    client = _login(saved_token)
    with connect() as connection:
        save_token(connection, client.client.dumps(), client.profile_id, key_material)
    user_id = client.profile_id if isinstance(client.profile_id, int) else "unknown"
    refreshed: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for day in days:
        try:
            downloaded = _archive_day(client, user_id, day)
        except GarminConnectTooManyRequestsError:
            failed.append({"day": day, "error": "GarminConnectTooManyRequestsError"})
            break
        except Exception as error:
            logger.warning("Day refresh failed: %s %s", day, type(error).__name__)
            failed.append({"day": day, "error": type(error).__name__})
            continue
        refreshed.append({"day": day, "sleep_downloaded": downloaded == 1})
        logger.info("refreshed %s sleep_downloaded=%s", day, downloaded == 1)
    return {
        "day_count": len(days),
        "refreshed_count": len(refreshed),
        "failed": failed,
        "days": refreshed,
    }


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
        for activity in activities:
            if isinstance(activity, dict):
                _remember_hr_zones(activity)
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


def archive_period(start: str, end: str) -> dict[str, Any]:
    start_date, end_date = parse_period(start, end)
    key_material = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    if not key_material:
        raise EncryptionKeyMissing

    with connect() as connection:
        ensure_schema(connection)
        saved_token = load_token(connection, key_material)

    client = _login(saved_token)
    with connect() as connection:
        save_token(connection, client.client.dumps(), client.profile_id, key_material)

    activities = client.get_activities_by_date(start_date.isoformat(), end_date.isoformat())
    if not isinstance(activities, list):
        raise ArchiveError("Activity list was not a list")

    user_id = client.profile_id if isinstance(client.profile_id, int) else "unknown"
    archived: list[dict[str, Any]] = []
    downloaded_activities = 0
    for activity in activities:
        if not isinstance(activity, dict):
            continue
        try:
            activity_id = _activity_id(activity)
            day = _activity_day(activity)
        except ArchiveError:
            continue
        if day < start_date.isoformat() or day > end_date.isoformat():
            continue
        _remember_activity(activity_id, _activity_name(activity), _activity_start(activity))
        _remember_hr_zones(activity)
        with connect() as connection:
            existing = find_activity_raw_object(connection, activity_id)
        stored = False
        if existing is None:
            zip_bytes = client.download_activity(
                str(activity_id),
                dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL,
            )
            if not isinstance(zip_bytes, (bytes, bytearray)):
                raise ArchiveError("Activity download was not bytes")
            with connect() as connection:
                _store_bytes(
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
            stored = True
            downloaded_activities += 1
        archived.append(
            {
                "garmin_activity_id": activity_id,
                "day": day,
                "stored": stored,
            }
        )

    downloaded_days = 0
    current = start_date
    while current <= end_date:
        day = current.isoformat()
        downloaded_days += _archive_day(client, user_id, day)
        current += timedelta(days=1)

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "activity_count": len(archived),
        "downloaded_activity_count": downloaded_activities,
        "activities": archived,
        "day_count": (end_date - start_date).days + 1,
        "downloaded_day_count": downloaded_days,
    }


def parse_period(start: str, end: str) -> tuple[date, date]:
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError) as error:
        raise PeriodError("Period dates must be YYYY-MM-DD") from error
    if end_date < start_date:
        raise PeriodError("Period end is before start")
    if (end_date - start_date).days + 1 > _MAX_PERIOD_DAYS:
        raise PeriodError("Period is longer than 14 days")
    return start_date, end_date


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
        _remember_activity(activity_id, _activity_name(activity), _activity_start(activity))
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


def _remember_activity(
    garmin_activity_id: int, garmin_name: str | None, start_local: str | None
) -> None:
    with connect() as connection:
        ensure_schema(connection)
        upsert_activity_meta(connection, garmin_activity_id, garmin_name, start_local)


def _archive_day(client: Garmin, user_id: int | str, day: str) -> int:
    with connect() as connection:
        existing = find_day_raw_object(connection, day)
    sleep, heart = _stored_sleep(existing)
    downloaded = 0
    if sleep is None or heart is None:
        sleep = client.get_sleep_data(day)
        heart = client.get_heart_rates(day)
        downloaded = 1
    document: dict[str, Any] = {"sleep": sleep, "heart_rate": heart}
    document.update(_daily_sections(client, day))
    body = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode()
    with connect() as connection:
        record = _store_bytes(
            connection,
            body=body,
            kind="day",
            source_format="json",
            pathname=f"garmin/{user_id}/day/{day}",
            extension="json",
            content_type="application/json",
            garmin_activity_id=None,
            day=day,
        )
        write_day_metrics(connection, date.fromisoformat(day), day_metrics(document), record)
    return downloaded


def _stored_sleep(existing: dict[str, Any] | None) -> tuple[Any, Any]:
    if existing is None:
        return None, None
    try:
        payload = json.loads(get_private(existing["source_path"]))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        logger.warning("Stored day file could not be read")
        return None, None
    except Exception as error:
        logger.warning("Stored day file could not be read: %s", type(error).__name__)
        return None, None
    if not isinstance(payload, dict):
        return None, None
    sleep = payload.get("sleep")
    heart = payload.get("heart_rate")
    if not isinstance(sleep, dict) or not isinstance(heart, dict):
        return None, None
    if not _has_sleep_duration(sleep) or not _has_resting_hr(heart):
        return None, None
    return sleep, heart


def _has_sleep_duration(sleep: dict[str, Any]) -> bool:
    daily = sleep.get("dailySleepDTO")
    if not isinstance(daily, dict):
        return False
    return _is_number(daily.get("sleepTimeSeconds"))


def _has_resting_hr(heart: dict[str, Any]) -> bool:
    return _is_number(heart.get("restingHeartRate"))


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _daily_sections(client: Garmin, day: str) -> dict[str, Any]:
    calls = (
        ("hrv", lambda: without_hrv_readings(client.get_hrv_data(day))),
        ("training_readiness", lambda: client.get_training_readiness(day)),
        ("daily_training_status", lambda: client.get_daily_training_status(day)),
        ("max_metrics", lambda: client.get_max_metrics(day)),
        ("four_week_load_balance", lambda: client.get_training_four_week_load_balance(day)),
        ("running_tolerance", lambda: client.get_running_tolerance(day, day, "daily")),
    )
    found: dict[str, Any] = {}
    for key, read in calls:
        try:
            value = read()
        except Exception as error:
            logger.warning("Daily Garmin read failed: %s %s", key, type(error).__name__)
            continue
        if value is None:
            continue
        found[key] = value
    return found


def list_hr_zone_seconds(activity: dict[str, Any]) -> dict[str, float]:
    found: dict[str, float] = {}
    for zone in range(1, 6):
        value = activity.get(f"hrTimeInZone_{zone}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        found[f"hr_zone_{zone}_sec"] = float(value)
    return found


def list_power_zone_seconds(activity: dict[str, Any]) -> dict[str, float]:
    found: dict[str, float] = {}
    for zone in range(1, 8):
        value = activity.get(f"powerTimeInZone_{zone}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        found[f"power_zone_{zone}_sec"] = float(value)
    return found


def _remember_hr_zones(activity: dict[str, Any]) -> None:
    try:
        activity_id = _activity_id(activity)
    except ArchiveError:
        return
    heart = list_hr_zone_seconds(activity)
    power = list_power_zone_seconds(activity)
    if not heart and not power:
        return
    with connect() as connection:
        ensure_schema(connection)
        if heart:
            save_hr_zone_seconds(connection, activity_id, heart)
        if power:
            save_power_zone_seconds(connection, activity_id, power)


def _activity_name(activity: dict[str, Any]) -> str | None:
    name = activity.get("activityName")
    if not isinstance(name, str):
        return None
    text = name.strip()
    return text or None


def _activity_start(activity: dict[str, Any]) -> str | None:
    start = activity.get("startTimeLocal") or activity.get("startTimeGMT")
    if not isinstance(start, str):
        return None
    text = start.strip().replace("T", " ")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        return None
    clock = text[11:19] if len(text) >= 19 else "00:00:00"
    if len(clock) != 8 or clock[2] != ":" or clock[5] != ":":
        clock = "00:00:00"
    return f"{text[:10]} {clock}"


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
    "PeriodError",
    "archive_latest",
    "archive_period",
    "parse_period",
]
