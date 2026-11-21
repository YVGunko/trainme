"""Read the current Garmin athlete profile and keep a version when it changes."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.profile_version import normalize_garmin, with_garmin_profile
from app.storage.blob import put_private
from app.storage.db import (
    connect,
    ensure_schema,
    find_raw_object,
    insert_athlete_profile_version,
    insert_raw_object,
    load_latest_athlete_profile,
)

logger = logging.getLogger(__name__)


def read_garmin_profile(client: Any) -> dict[str, Any]:
    """Call the four current-profile reads. None of them is dated by Garmin."""
    return {
        "user_settings": client.get_user_profile(),
        "hr_zones": client.get_heart_rate_zones(),
        "power_zones": client.get_power_zones(),
        "cycling_ftp": client.get_cycling_ftp(),
    }


def record_garmin_profile(client: Any) -> dict[str, Any]:
    """Store one new profile row when the normalized Garmin fields changed.

    The athlete's notes and excluded sports are copied from the latest row.
    A profile that matches that row is left untouched.
    """
    try:
        raw = read_garmin_profile(client)
    except Exception as error:
        logger.warning("Garmin profile read failed: %s", type(error).__name__)
        return {"stored": False, "error": type(error).__name__}
    garmin = normalize_garmin(raw)
    if garmin is None:
        return {"stored": False, "error": "unreadable"}
    body = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()
    sha256 = hashlib.sha256(body).hexdigest()
    try:
        with connect() as connection:
            ensure_schema(connection)
            latest = load_latest_athlete_profile(connection)
            version = with_garmin_profile(latest, garmin, sha256)
            if version is None:
                return {"stored": False, "content_hash": latest.get("content_hash") if latest else None}
            _store_raw(connection, client, sha256, body)
            stored = insert_athlete_profile_version(connection, version)
    except Exception as error:
        logger.warning("Garmin profile store failed: %s", type(error).__name__)
        return {"stored": False, "error": type(error).__name__}
    return {"stored": True, "recorded_at": stored["recorded_at"], "content_hash": stored["content_hash"]}


def _store_raw(connection: Any, client: Any, sha256: str, body: bytes) -> None:
    if find_raw_object(connection, sha256) is not None:
        return
    user_id = client.profile_id if isinstance(getattr(client, "profile_id", None), int) else "unknown"
    path = put_private(f"garmin/{user_id}/profile/{sha256}.json", body, "application/json")
    insert_raw_object(
        connection,
        {
            "kind": "profile",
            "garmin_activity_id": None,
            "day": None,
            "source_format": "json",
            "source_path": path,
            "source_sha256": sha256,
            "byte_size": len(body),
        },
    )
