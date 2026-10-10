import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any

from app.normalize.day import day_metrics
from app.normalize.fit import NormalizeError, parse_activity_zip
from app.normalize.store import latest_activity_raw_object, latest_raw_object, write_normalized
from app.storage.blob import get_private
from app.storage.db import connect, ensure_schema, find_day_raw_object, load_activity_meta


def normalize_latest() -> dict[str, Any]:
    with connect() as connection:
        ensure_schema(connection)
        activity_raw = latest_raw_object(connection, "activity", "zip")
        day_raw = latest_raw_object(connection, "day", "json")
    if activity_raw is None or not isinstance(activity_raw["garmin_activity_id"], int):
        raise NormalizeError("No archived activity", 404)
    if day_raw is None or not isinstance(day_raw["day"], str):
        raise NormalizeError("No archived day", 404)

    zip_bytes = _download(activity_raw)
    day_bytes = _download(day_raw)
    fit_file, parsed = parse_activity_zip(zip_bytes)
    try:
        payload = json.loads(day_bytes)
    except json.JSONDecodeError as error:
        raise NormalizeError("Day file is not JSON") from error
    metrics = day_metrics(payload)

    with connect() as connection:
        summary = write_normalized(
            connection,
            garmin_activity_id=activity_raw["garmin_activity_id"],
            parsed=parsed,
            activity_source=activity_raw,
            day=date.fromisoformat(day_raw["day"]),
            day_fields=metrics,
            day_source=day_raw,
        )
    summary["fit_file"] = fit_file
    return summary


def normalize_activity(garmin_activity_id: int) -> dict[str, Any]:
    if garmin_activity_id < 1:
        raise NormalizeError("No archived activity", 400)
    with connect() as connection:
        ensure_schema(connection)
        activity_raw = latest_activity_raw_object(connection, garmin_activity_id)
        meta = load_activity_meta(connection, garmin_activity_id)
    if activity_raw is None:
        raise NormalizeError("No archived activity", 404)

    zip_bytes = _download(activity_raw)
    fit_file, parsed = parse_activity_zip(zip_bytes)
    day_text = None
    if meta is not None and isinstance(meta.get("start_local"), str):
        day_text = meta["start_local"][:10]
    else:
        day_text = _local_day(parsed.get("start_at"), parsed.get("timezone_offset_min"))

    day_raw = None
    day = None
    metrics: dict[str, float] = {}
    if day_text:
        with connect() as connection:
            day_raw = find_day_raw_object(connection, day_text)
        if day_raw is not None:
            day = date.fromisoformat(day_text)
            day_bytes = _download(day_raw)
            try:
                payload = json.loads(day_bytes)
            except json.JSONDecodeError as error:
                raise NormalizeError("Day file is not JSON") from error
            metrics = day_metrics(payload)

    with connect() as connection:
        summary = write_normalized(
            connection,
            garmin_activity_id=garmin_activity_id,
            parsed=parsed,
            activity_source=activity_raw,
            day=day,
            day_fields=metrics,
            day_source=day_raw,
        )
    summary["fit_file"] = fit_file
    return summary


def _local_day(start_at: Any, offset_min: Any) -> str | None:
    if not isinstance(start_at, datetime):
        return None
    offset = offset_min if isinstance(offset_min, int) else 0
    return (start_at + timedelta(minutes=offset)).date().isoformat()


def _download(raw: dict[str, Any]) -> bytes:
    body = get_private(raw["source_path"])
    if hashlib.sha256(body).hexdigest() != raw["source_sha256"]:
        raise NormalizeError("Downloaded bytes do not match the stored hash")
    return body
