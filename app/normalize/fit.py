import io
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

import fitdecode
from fitdecode.exceptions import FitHeaderError, FitParseError

_SEMICIRCLE_DEGREES = 180 / 2**31
_INVALID_SEMICIRCLE = 0x7FFFFFFF
_MAX_OFFSET_MIN = 14 * 60
_RIGHT_BALANCE = 0x8000
_BALANCE_MASK = 0x3FFF


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
    records: list[Any] = []
    grouped: dict[str, list[Any]] = {}
    try:
        with fitdecode.FitReader(io.BytesIO(payload)) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage) or not frame.name:
                    continue
                if frame.name == "record":
                    records.append(frame)
                else:
                    grouped.setdefault(frame.name, []).append(frame)
    except (FitHeaderError, FitParseError) as error:
        raise NormalizeError("FIT file could not be read") from error
    sessions = grouped.get("session") or []
    if not sessions:
        raise NormalizeError("FIT file has no session")
    return _session(sessions[0], grouped, records)


def _session(session: Any, grouped: dict[str, list[Any]], records: list[Any]) -> dict[str, Any]:
    start = _datetime(session, "start_time")
    elapsed = _number(session, "total_elapsed_time", "s")
    sport = _text(session, "sport")
    activity = (grouped.get("activity") or [None])[0]
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
        "garmin_activity_load": _unitless(session, "training_load_peak"),
        "running": _running(session, sport),
        "cycling": _cycling(session, sport),
        "sets": _strength_sets(grouped.get("set") or [], grouped.get("exercise_title") or []),
        "fields": _all_fields(grouped),
        "samples": _samples(records),
    }
    parsed.update(_zones(session))
    return parsed


def _all_fields(grouped: dict[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for message_name in sorted(grouped):
        for index, message in enumerate(grouped[message_name]):
            rows.extend(_facts(message_name, index, message))
    return rows


def _facts(message_name: str, message_index: int, message: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for field in message.fields:
        for row in _fact_values(message_name, message_index, field):
            key = (row["name"], row["ordinal"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def _fact_values(message_name: str, message_index: int, field: Any) -> list[dict[str, Any]]:
    if isinstance(field.value, (list, tuple)):
        rows: list[dict[str, Any]] = []
        for ordinal, item in enumerate(field.value):
            row = _one_fact(message_name, message_index, field.name, ordinal, item, field.units)
            if row is not None:
                rows.append(row)
        return rows
    row = _one_fact(message_name, message_index, field.name, 0, field.value, field.units)
    return [] if row is None else [row]


def _one_fact(
    message_name: str,
    message_index: int,
    name: str,
    ordinal: int,
    value: Any,
    units: str | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    number, unit = _stored_number(value, units)
    if number is not None:
        return {
            "message": message_name,
            "message_index": message_index,
            "name": name,
            "ordinal": ordinal,
            "value_num": number,
            "value_text": None,
            "unit": unit,
        }
    if isinstance(value, datetime):
        text = value.astimezone(timezone.utc).isoformat()
    elif isinstance(value, str):
        if not value:
            return None
        text = value
    elif isinstance(value, bool):
        return {
            "message": message_name,
            "message_index": message_index,
            "name": name,
            "ordinal": ordinal,
            "value_num": float(value),
            "value_text": None,
            "unit": units,
        }
    else:
        text = str(value)
    return {
        "message": message_name,
        "message_index": message_index,
        "name": name,
        "ordinal": ordinal,
        "value_num": None,
        "value_text": text,
        "unit": None if units == "semicircles" else units,
    }


def _stored_number(value: Any, units: str | None) -> tuple[float | None, str | None]:
    if not _is_number(value):
        return None, None
    if units == "semicircles":
        if int(value) == _INVALID_SEMICIRCLE:
            return None, None
        return float(value) * _SEMICIRCLE_DEGREES, "deg"
    return float(value), units


def _running(session: Any, sport: str | None) -> dict[str, float | None] | None:
    if sport != "running":
        return None
    # FIT avg_running_cadence is strides/min. Garmin Connect shows steps/min = 2x.
    # FIT avg_step_length is millimetres. Connect stride length is twice that.
    strides = _cadence_sum(session, "avg_running_cadence", "strides/min", "avg_fractional_cadence")
    if strides is None:
        strides = _cadence_sum(session, "avg_cadence", "strides/min", "avg_fractional_cadence")
    max_strides = _number(session, "max_running_cadence", "strides/min")
    if max_strides is None:
        max_strides = _number(session, "max_cadence", "strides/min")
    step_mm = _number(session, "avg_step_length", "mm")
    oscillation = _number(session, "avg_vertical_oscillation", "mm")
    return {
        "avg_cadence_spm": None if strides is None else strides * 2,
        "max_cadence_spm": None if max_strides is None else max_strides * 2,
        "avg_step_length_mm": step_mm,
        "avg_stride_length_cm": None if step_mm is None else step_mm * 2 / 10,
        "elevation_gain_m": _number(session, "total_ascent", "m"),
        "total_descent_m": _number(session, "total_descent", "m"),
        "avg_ground_contact_time_ms": _number(session, "avg_stance_time", "ms"),
        "avg_vertical_oscillation_cm": None if oscillation is None else oscillation / 10,
        "avg_vertical_ratio": _number(session, "avg_vertical_ratio", "percent"),
        "avg_stance_time_percent": _number(session, "avg_stance_time_percent", "percent"),
        "avg_stance_time_balance": _number(session, "avg_stance_time_balance", "percent"),
        "avg_power_w": _number(session, "avg_power", "watts"),
        "max_power_w": _number(session, "max_power", "watts"),
        "normalized_power_w": _number(session, "normalized_power", "watts"),
        "avg_respiration": _number(session, "enhanced_avg_respiration_rate", "Breaths/min"),
        "max_respiration": _number(session, "enhanced_max_respiration_rate", "Breaths/min"),
        "total_strides": _number(session, "total_strides", "strides"),
    }


def _cycling(session: Any, sport: str | None) -> dict[str, float | None] | None:
    if sport != "cycling":
        return None
    return {
        "avg_power_w": _number(session, "avg_power", "watts"),
        "max_power_w": _number(session, "max_power", "watts"),
        "normalized_power_w": _number(session, "normalized_power", "watts"),
        "intensity_factor": _number(session, "intensity_factor", "if"),
        "tss": _number(session, "training_stress_score", "tss"),
        "avg_cadence_rpm": _cadence_sum(session, "avg_cadence", "rpm", "avg_fractional_cadence"),
        "max_cadence_rpm": _cadence_sum(session, "max_cadence", "rpm", "max_fractional_cadence"),
        "total_work_j": _number(session, "total_work", "J"),
        "threshold_power_w": _number(session, "threshold_power", "watts"),
        "left_power_pct": _left_power_pct(session),
        "avg_left_torque_effectiveness": _number(session, "avg_left_torque_effectiveness", "percent"),
        "avg_right_torque_effectiveness": _number(session, "avg_right_torque_effectiveness", "percent"),
        "avg_left_pedal_smoothness": _number(session, "avg_left_pedal_smoothness", "percent"),
        "avg_right_pedal_smoothness": _number(session, "avg_right_pedal_smoothness", "percent"),
        "avg_combined_pedal_smoothness": _number(session, "avg_combined_pedal_smoothness", "percent"),
        "total_ascent_m": _number(session, "total_ascent", "m"),
        "total_descent_m": _number(session, "total_descent", "m"),
    }


def _strength_sets(sets: list[Any], titles: list[Any]) -> list[dict[str, Any]]:
    names: dict[int, str] = {}
    for title in titles:
        index = _message_index(title)
        name = _text(title, "wkt_step_name")
        if index is not None and name:
            names[index] = name
    rows: list[dict[str, Any]] = []
    for index, message in enumerate(sets):
        category = _category_name(message)
        subtype = _count(message, "category_subtype")
        step = _count(message, "wkt_step_index")
        exercise = names.get(int(step)) if step is not None and int(step) in names else None
        if exercise is None:
            exercise = _exercise_name(category, subtype)
        rows.append(
            {
                "set_index": index,
                "set_type": _text(message, "set_type"),
                "category": category,
                "exercise": exercise,
                "repetitions": _count(message, "repetitions"),
                "weight_kg": _number(message, "weight", "kg"),
                "duration_sec": _number(message, "duration", "s"),
                "start_at": _datetime(message, "start_time"),
            }
        )
    return rows


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


def _record_points(record: Any) -> list[tuple[str, float, str | None]]:
    points: list[tuple[str, float, str | None]] = []
    seen: set[str] = set()
    for field in record.fields:
        if field.name == "timestamp" or field.name in seen:
            continue
        values = field.value if isinstance(field.value, (list, tuple)) else [field.value]
        for ordinal, value in enumerate(values):
            number, unit = _stored_number(value, field.units)
            if number is None:
                continue
            name = field.name if len(values) == 1 else f"{field.name}_{ordinal}"
            if name in seen:
                continue
            seen.add(name)
            points.append((name, number, unit))
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


def _cadence_sum(session: Any, name: str, units: str, fractional_name: str) -> float | None:
    base = _number(session, name, units)
    extra = _number(session, fractional_name, "rpm")
    if base is None:
        return None
    if extra is None:
        return base
    return base + extra


def _left_power_pct(session: Any) -> float | None:
    field = _field(session, "left_right_balance")
    if field is None or not _is_number(field.value):
        return None
    raw = int(field.value)
    percent = (raw & _BALANCE_MASK) / 100
    if raw & _RIGHT_BALANCE:
        return 100 - percent
    return percent


def _category_name(message: Any) -> str | None:
    field = _field(message, "category")
    if field is None:
        return None
    if isinstance(field.value, str) and field.value:
        return field.value
    if _is_number(field.value):
        enum = fitdecode.profile.FIELD_TYPES["exercise_category"].enum
        name = enum.get(int(field.value))
        return name if isinstance(name, str) else None
    return None


def _exercise_name(category: str | None, subtype: float | None) -> str | None:
    if category is None or subtype is None:
        return None
    field_type = fitdecode.profile.FIELD_TYPES.get(f"{category}_exercise_name")
    if field_type is None:
        return None
    name = field_type.enum.get(int(subtype))
    return name if isinstance(name, str) else None


def _message_index(message: Any) -> int | None:
    value = _count(message, "message_index")
    if value is None:
        return None
    return int(value) & 0x0FFF


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


def _count(message: Any, name: str) -> float | None:
    field = _field(message, name)
    if field is None or field.units not in (None, "") or not _is_number(field.value):
        return None
    return float(field.value)


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
