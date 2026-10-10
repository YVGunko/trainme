import io
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

import fitdecode
from fitdecode.exceptions import FitHeaderError, FitParseError

_SEMICIRCLE_DEGREES = 180 / 2**31
_MAX_OFFSET_MIN = 14 * 60


class NormalizeError(Exception):
    """Raised when a stored Garmin file cannot be turned into rows."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def parse_activity_zip(payload: bytes) -> tuple[str, dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise NormalizeError("Activity file is not a zip") from error
    names = [
        name
        for name in archive.namelist()
        if name.lower().endswith(".fit") and not name.endswith("/")
    ]
    if not names:
        raise NormalizeError("ZIP does not contain a FIT file")
    chosen = max(names, key=lambda name: archive.getinfo(name).file_size)
    return chosen, parse_fit(archive.read(chosen))


def parse_fit(payload: bytes) -> dict[str, Any]:
    session = None
    activity = None
    records: list[Any] = []
    try:
        with fitdecode.FitReader(io.BytesIO(payload)) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage) or not frame.name:
                    continue
                if frame.name == "session" and session is None:
                    session = frame
                elif frame.name == "activity" and activity is None:
                    activity = frame
                elif frame.name == "record":
                    records.append(frame)
    except (FitHeaderError, FitParseError) as error:
        raise NormalizeError("FIT file could not be read") from error
    if session is None:
        raise NormalizeError("FIT file has no session")
    return _session(session, activity, records)


def _session(session: Any, activity: Any, records: list[Any]) -> dict[str, Any]:
    start = _datetime(session, "start_time")
    elapsed = _number(session, "total_elapsed_time", "s")
    sport = _text(session, "sport")
    parsed: dict[str, Any] = {
        "sport": sport,
        "sub_sport": _text(session, "sub_sport"),
        "garmin_type_key": None,
        "start_at": start,
        "end_at": start + timedelta(seconds=elapsed) if start is not None and elapsed is not None else None,
        "duration_sec": _number(session, "total_timer_time", "s"),
        "moving_duration_sec": _number(session, "total_moving_time", "s"),
        "elapsed_duration_sec": elapsed,
        "timezone_offset_min": _offset_min(activity),
        "distance_m": _number(session, "total_distance", "m"),
        "avg_hr": _number(session, "avg_heart_rate", "bpm"),
        "max_hr": _number(session, "max_heart_rate", "bpm"),
        "avg_speed": _speed(session),
        "calories": _number(session, "total_calories", "kcal"),
        "aerobic_effect": _unitless(session, "total_training_effect"),
        "anaerobic_effect": _unitless(session, "total_anaerobic_training_effect"),
        "training_effect_label": None,
        "garmin_activity_load": None,
        "running": _running(session, sport),
        "samples": _samples(records),
    }
    parsed.update(_zones(session))
    return parsed


def _running(session: Any, sport: str | None) -> dict[str, float | None] | None:
    if sport != "running":
        return None
    oscillation = _number(session, "avg_vertical_oscillation", "mm")
    # FIT running cadence is strides/min and step length is millimetres.
    # avg_cadence_spm and avg_stride_length_cm stay empty.
    return {
        "avg_cadence_spm": None,
        "elevation_gain_m": _number(session, "total_ascent", "m"),
        "avg_ground_contact_time_ms": _number(session, "avg_stance_time", "ms"),
        "avg_vertical_oscillation_cm": None if oscillation is None else oscillation / 10,
        "avg_stride_length_cm": None,
    }


def _samples(records: list[Any]) -> list[dict[str, Any]]:
    keyed: dict[tuple[datetime, str], dict[str, Any]] = {}
    for record in records:
        timestamp = _datetime(record, "timestamp")
        if timestamp is None:
            continue
        for metric, value, unit in _record_points(record):
            keyed[(timestamp, metric)] = {
                "timestamp": timestamp,
                "metric": metric,
                "value": value,
                "unit": unit,
            }
    return [keyed[key] for key in sorted(keyed)]


def _record_points(record: Any) -> list[tuple[str, float, str]]:
    points: list[tuple[str, float, str]] = []
    heart_rate = _number(record, "heart_rate", "bpm")
    if heart_rate is not None:
        points.append(("heart_rate", heart_rate, "bpm"))
    cadence = _field(record, "cadence")
    if cadence is not None and cadence.units in {"rpm", "strides/min"} and _is_number(cadence.value):
        points.append(("cadence", float(cadence.value), cadence.units))
    speed = _number(record, "enhanced_speed", "m/s")
    if speed is None:
        speed = _number(record, "speed", "m/s")
    if speed is not None:
        points.append(("speed", speed, "m/s"))
    power = _number(record, "power", "watts")
    if power is not None:
        points.append(("power", power, "watts"))
    stance = _number(record, "stance_time", "ms")
    if stance is not None:
        points.append(("stance_time", stance, "ms"))
    oscillation = _number(record, "vertical_oscillation", "mm")
    if oscillation is not None:
        points.append(("vertical_oscillation", oscillation, "mm"))
    step = _number(record, "step_length", "mm")
    if step is not None:
        points.append(("step_length", step, "mm"))
    latitude = _degrees(record, "position_lat")
    longitude = _degrees(record, "position_long")
    if latitude is not None:
        points.append(("gps_lat", latitude, "deg"))
    if longitude is not None:
        points.append(("gps_lon", longitude, "deg"))
    return points


def _zones(session: Any) -> dict[str, float]:
    field = _field(session, "time_in_hr_zone")
    if field is None or field.units != "s" or not isinstance(field.value, (list, tuple)):
        return {}
    zones: dict[str, float] = {}
    for index, value in enumerate(field.value[:5], start=1):
        if _is_number(value):
            zones[f"hr_zone_{index}_sec"] = float(value)
    return zones


def _speed(session: Any) -> float | None:
    enhanced = _number(session, "enhanced_avg_speed", "m/s")
    if enhanced is not None:
        return enhanced
    return _number(session, "avg_speed", "m/s")


def _offset_min(activity: Any) -> int | None:
    if activity is None:
        return None
    local = _datetime(activity, "local_timestamp")
    stamp = _datetime(activity, "timestamp")
    if local is None or stamp is None:
        return None
    offset = int(round((local - stamp).total_seconds() / 60))
    if abs(offset) > _MAX_OFFSET_MIN:
        return None
    return offset


def _datetime(message: Any, name: str) -> datetime | None:
    field = _field(message, name)
    if field is None or not isinstance(field.value, datetime):
        return None
    if field.value.tzinfo is None:
        return field.value.replace(tzinfo=timezone.utc)
    return field.value.astimezone(timezone.utc)


def _text(message: Any, name: str) -> str | None:
    field = _field(message, name)
    if field is None or not isinstance(field.value, str) or not field.value:
        return None
    return field.value


def _unitless(message: Any, name: str) -> float | None:
    field = _field(message, name)
    if field is None or field.units is not None or not _is_number(field.value):
        return None
    return float(field.value)


def _degrees(message: Any, name: str) -> float | None:
    field = _field(message, name)
    if field is None or field.units != "semicircles" or not _is_number(field.value):
        return None
    if int(field.value) == 0x7FFFFFFF:
        return None
    return float(field.value) * _SEMICIRCLE_DEGREES


def _number(message: Any, name: str, units: str) -> float | None:
    field = _field(message, name)
    if field is None or field.units != units or not _is_number(field.value):
        return None
    return float(field.value)


def _field(message: Any, name: str) -> Any:
    try:
        return message.get_field(name)
    except KeyError:
        return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
