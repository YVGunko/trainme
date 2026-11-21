"""One canonical athlete profile and its fingerprint.

A new database row is written only when this fingerprint changes. The same
numbers must hash the same way whether they were just read from Garmin or
loaded back from Postgres, so every quantity is rendered with one decimal.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

_FIELDS = (
    "notes",
    "avoided_sports",
    "birth_date",
    "weight_kg",
    "height_cm",
    "cycling_ftp",
    "hr_zones",
    "power_zones",
)


def empty_profile() -> dict[str, Any]:
    return {
        "notes": None,
        "avoided_sports": [],
        "birth_date": None,
        "weight_kg": None,
        "height_cm": None,
        "cycling_ftp": None,
        "hr_zones": [],
        "power_zones": [],
    }


def profile_hash(snapshot: dict[str, Any]) -> str:
    """Return the fingerprint of the profile fields, ignoring bookkeeping."""
    encoded = json.dumps(
        _canonical(snapshot), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def with_written_profile(
    latest: dict[str, Any] | None, notes: str | None, avoided_sports: list[str]
) -> dict[str, Any] | None:
    """Return a new snapshot when the athlete's own text changed."""
    base = dict(latest or empty_profile())
    return _if_changed(
        latest,
        {**base, "notes": notes, "avoided_sports": list(avoided_sports)},
        source_sha256=base.get("source_sha256"),
    )


def with_garmin_profile(
    latest: dict[str, Any] | None,
    garmin: dict[str, Any],
    source_sha256: str | None,
) -> dict[str, Any] | None:
    """Return a new snapshot when the Garmin side changed. Notes stay as stored."""
    base = dict(latest or empty_profile())
    merged = {**base, **garmin, "notes": base.get("notes"), "avoided_sports": list(base.get("avoided_sports") or [])}
    return _if_changed(latest, merged, source_sha256=source_sha256)


def normalize_garmin(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Read age inputs, weight, FTP, and zone bounds from the four Garmin replies.

    ``None`` means the user-settings reply was not an object, so there is nothing
    safe to store. Zone lists may be empty when Garmin has none configured.
    """
    settings = raw.get("user_settings")
    if not isinstance(settings, dict):
        return None
    user = settings.get("userData")
    if not isinstance(user, dict):
        user = {}
    return {
        "birth_date": _birth_date(user.get("birthDate")),
        "weight_kg": _weight_kg(user.get("weight")),
        "height_cm": _height_cm(user.get("height")),
        "cycling_ftp": _ftp(raw.get("cycling_ftp")),
        "hr_zones": _zones(raw.get("hr_zones")),
        "power_zones": _zones(raw.get("power_zones")),
    }


def _if_changed(
    latest: dict[str, Any] | None,
    snapshot: dict[str, Any],
    source_sha256: str | None,
) -> dict[str, Any] | None:
    prepared = empty_profile()
    prepared.update({key: snapshot.get(key) for key in _FIELDS})
    prepared["avoided_sports"] = list(prepared["avoided_sports"] or [])
    prepared["hr_zones"] = list(prepared["hr_zones"] or [])
    prepared["power_zones"] = list(prepared["power_zones"] or [])
    digest = profile_hash(prepared)
    if latest is not None and latest.get("content_hash") == digest:
        return None
    prepared["content_hash"] = digest
    prepared["source_sha256"] = source_sha256
    return prepared


def _canonical(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "notes": snapshot.get("notes"),
        "avoided_sports": list(snapshot.get("avoided_sports") or []),
        "birth_date": _date_text(snapshot.get("birth_date")),
        "weight_kg": _decimal(snapshot.get("weight_kg")),
        "height_cm": _decimal(snapshot.get("height_cm")),
        "cycling_ftp": _decimal(snapshot.get("cycling_ftp")),
        "hr_zones": _canonical_zones(snapshot.get("hr_zones")),
        "power_zones": _canonical_zones(snapshot.get("power_zones")),
    }


def _canonical_zones(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    found = []
    for item in value:
        if not isinstance(item, dict):
            continue
        floors = [_decimal(step) for step in item.get("floors") or []]
        entry: dict[str, Any] = {"sport": item.get("sport"), "floors": floors}
        ceiling = _decimal(item.get("ceiling"))
        if ceiling is not None:
            entry["ceiling"] = ceiling
        found.append(entry)
    return found


def _decimal(value: Any) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return f"{number:.1f}"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _date_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return None


def _birth_date(value: Any) -> str | None:
    text = _date_text(value)
    if text is None:
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _weight_kg(value: Any) -> float | None:
    """Garmin sends body weight in grams. A small number is already kilograms."""
    number = _number(value)
    if number is None:
        return None
    if number > 500:
        return round(number / 1000, 1)
    return number


def _height_cm(value: Any) -> float | None:
    """Garmin sends height in centimetres. A value below 3 is metres."""
    number = _number(value)
    if number is None:
        return None
    if number < 3:
        return round(number * 100, 1)
    return number


def _ftp(payload: Any) -> float | None:
    if isinstance(payload, list):
        cycling = [
            item
            for item in payload
            if isinstance(item, dict) and str(item.get("sport", "")).upper() == "CYCLING"
        ]
        payload = cycling[0] if cycling else next((item for item in payload if isinstance(item, dict)), None)
    if not isinstance(payload, dict):
        return _number(payload)
    for key in ("functionalThresholdPower", "ftp", "value"):
        number = _number(payload.get(key))
        if number is not None:
            return number
    return None


def _zones(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        nested = payload.get("zones")
        items = nested if isinstance(nested, list) else [payload]
    else:
        return []
    found: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sport = item.get("sport") or item.get("sportTypeKey") or "DEFAULT"
        floors: list[float] = []
        for index in range(1, 8):
            number = _number(item.get(f"zone{index}Floor"))
            if number is None:
                break
            floors.append(number)
        if not floors:
            continue
        entry: dict[str, Any] = {"sport": str(sport).upper(), "floors": floors}
        ceiling_key = "zone5Ceiling" if len(floors) <= 5 else "zone7Ceiling"
        ceiling = _number(item.get(ceiling_key))
        if ceiling is None:
            ceiling = _number(item.get("maxHeartRate"))
        if ceiling is not None:
            entry["ceiling"] = ceiling
        found.append(entry)
    found.sort(key=lambda item: str(item["sport"]))
    return found
