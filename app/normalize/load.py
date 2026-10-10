import hashlib
import json
from datetime import date
from typing import Any

from app.normalize.day import day_metrics
from app.normalize.fit import NormalizeError, parse_activity_zip
from app.normalize.store import latest_raw_object, write_normalized
from app.storage.blob import get_private
from app.storage.db import connect, ensure_schema


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


def _download(raw: dict[str, Any]) -> bytes:
    body = get_private(raw["source_path"])
    if hashlib.sha256(body).hexdigest() != raw["source_sha256"]:
        raise NormalizeError("Downloaded bytes do not match the stored hash")
    return body
