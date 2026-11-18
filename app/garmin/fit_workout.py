"""Read a Garmin FIT workout file into the app workout description.

The result uses the same keys as the description accepted by
``app.garmin.workout.build_workout``, so a FIT file goes through the existing
sport, step, target, and exercise checks before anything is sent to Garmin.

Only the parts of a workout this app can express are read. A step with an
unsupported duration, target, or exercise stops the import with
``WorkoutFitError`` instead of being dropped.
"""

from __future__ import annotations

import io
from typing import Any

import fitdecode
from fitdecode.exceptions import FitError
from fitdecode.profile import FIELD_TYPES

from garminconnect import exercises

_FILE_TYPE_WORKOUT = "workout"
_FILE_TYPE_ACTIVITY = "activity"

# FIT carries a base sport and a sub sport. The workout description has one
# sport, so a running or cycling sub sport (trail, indoor, ...) maps to the
# base sport. A Garmin mobility workout has no FIT sport of its own and uses
# flexibility training.
_BASE_SPORTS = {"running": "running", "cycling": "cycling"}
_TRAINING_SUB_SPORTS = {
    "strength_training": "strength_training",
    "yoga": "yoga",
    "flexibility_training": "mobility",
}

_KINDS = {
    "warmup": "warmup",
    "cooldown": "cooldown",
    "recovery": "recovery",
    "rest": "rest",
    "interval": "interval",
    "active": "interval",
    "other": "interval",
}
_TIMED_KINDS = {"warmup", "cooldown", "recovery", "rest"}
# Garmin plans put a power or heart-rate target on a warmup, recovery, or
# cooldown step too, so a target does not mean interval.
_TARGETABLE_KINDS = {"interval", "warmup", "recovery", "cooldown"}

# A custom FIT target holds percent of the user's maximum up to this value and
# beats per minute plus it above it. Power uses percent of threshold power up
# to 1000 and watts plus it above it.
_BPM_OFFSET = 100
_WATTS_OFFSET = 1000

_display_names: dict[tuple[str, str], str] | None = None

_step_name_field = 0
_duration_field = 1
_duration_value_field = 2
_target_field = 3
_target_value_field = 4
_target_low_field = 5
_target_high_field = 6
_intensity_field = 7
_notes_field = 8
_category_field = 10
_exercise_field = 11
_weight_field = 12
_secondary_target_field = 19
_secondary_target_value_field = 20
_secondary_low_field = 21
_secondary_high_field = 22
_index_field = 254


class WorkoutFitError(Exception):
    """Raised when a FIT file is not a workout this app can send.

    ``reason`` is a short code the web layer turns into a sentence, so the
    caller is told what is wrong with the file instead of a generic refusal.
    """

    def __init__(self, message: str, reason: str = "not_a_workout") -> None:
        super().__init__(message)
        self.reason = reason


def parse_workout_fit(payload: bytes) -> tuple[dict[str, Any], list[str]]:
    """Return the workout description and what the description could not hold."""
    workbook, steps = _read(payload)
    name = _text(workbook, 8)
    if name is None:
        raise WorkoutFitError("FIT workout has no name")
    spec: dict[str, Any] = {
        "name": name,
        "sport": _sport(workbook),
        "blocks": _blocks(steps),
    }
    description = _text(workbook, 17)
    if description is not None:
        spec["description"] = description
    return spec, _warnings(steps)


def _read(payload: bytes) -> tuple[Any, list[tuple[int, Any]]]:
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise WorkoutFitError("FIT file is empty", "empty")
    workbook: Any = None
    steps: list[tuple[int, Any]] = []
    kind: Any = None
    try:
        with fitdecode.FitReader(io.BytesIO(bytes(payload))) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name == "file_id":
                    kind = _value(frame, 0)
                elif frame.name == "workout" and workbook is None:
                    workbook = frame
                elif frame.name == "workout_step":
                    steps.append((_step_index(len(steps), frame), frame))
    except FitError as error:
        raise WorkoutFitError("FIT file could not be read", "unreadable") from error
    except (OSError, ValueError) as error:
        raise WorkoutFitError("FIT file could not be read", "unreadable") from error
    if kind != _FILE_TYPE_WORKOUT:
        raise WorkoutFitError(_describe_other_file(kind), _other_reason(kind))
    if workbook is None:
        raise WorkoutFitError("FIT file has no workout message", "no_workout_message")
    return workbook, sorted(steps, key=lambda item: item[0])


def _other_reason(kind: Any) -> str:
    if kind is None:
        return "unreadable"
    if kind == _FILE_TYPE_ACTIVITY:
        return "activity_file"
    return "other_file"


def _describe_other_file(kind: Any) -> str:
    """Name what the file actually is, because the user picked it by hand."""
    if kind == _FILE_TYPE_ACTIVITY:
        return (
            "FIT file is an activity, not a workout. "
            "Garmin Connect imports activities separately and does not import workout files."
        )
    if isinstance(kind, str):
        return f"FIT file type is {kind}, not a workout"
    if kind is None:
        return "FIT file has no file_id message"
    return f"FIT file type id {kind} is not a workout"


def _sport(workbook: Any) -> str:
    sport = _text(workbook, 4)
    if sport in _BASE_SPORTS:
        return _BASE_SPORTS[sport]
    sub_sport = _text(workbook, 11)
    if sport == "training" and sub_sport in _TRAINING_SUB_SPORTS:
        return _TRAINING_SUB_SPORTS[sub_sport]
    raise WorkoutFitError(f"FIT workout sport is not supported: {sport}/{sub_sport}")


def _blocks(steps: list[tuple[int, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    placed: dict[int, int] = {}
    for index, frame in steps:
        if _text(frame, _duration_field) == "repeat_until_steps_cmplt":
            _close_repeat(units, placed, index, frame)
            continue
        if index in placed:
            raise WorkoutFitError(f"FIT step {index} appears twice")
        placed[index] = len(units)
        units.append({"steps": [_step(index, frame)]})
    blocks: list[dict[str, Any]] = []
    for unit in units:
        if blocks and "repeat" not in unit and "repeat" not in blocks[-1]:
            blocks[-1]["steps"].extend(unit["steps"])
            continue
        blocks.append(unit)
    if not blocks:
        raise WorkoutFitError("FIT workout has no steps")
    return blocks


def _close_repeat(
    units: list[dict[str, Any]],
    placed: dict[int, int],
    index: int,
    frame: Any,
) -> None:
    if _text(frame, _target_field) not in (None, "open"):
        raise WorkoutFitError(f"FIT repeat step {index} has a target")
    first = _number(frame, _duration_value_field)
    count = _number(frame, _target_value_field)
    if first is None or count is None:
        raise WorkoutFitError(f"FIT repeat step {index} is incomplete")
    start = placed.get(int(first))
    if start is None:
        raise WorkoutFitError(f"FIT repeat step {index} points at an unknown step")
    children = units[start:]
    if not children:
        raise WorkoutFitError(f"FIT repeat step {index} repeats no steps")
    if any("repeat" in unit for unit in children):
        raise WorkoutFitError("FIT file repeats a block that is already repeated")
    del units[start:]
    for key in [key for key, value in placed.items() if value >= start]:
        del placed[key]
    iterations = int(count)
    if iterations < 1:
        raise WorkoutFitError(f"FIT repeat step {index} repeats fewer than one time")
    repeated: list[dict[str, Any]] = []
    for unit in children:
        repeated.extend(unit["steps"])
    units.append({"repeat": iterations, "steps": repeated})


def _step(index: int, frame: Any) -> dict[str, Any]:
    kind = _kind(index, frame)
    step: dict[str, Any] = {"kind": kind, "end": _end(index, frame, kind)}
    exercise = _exercise(index, frame)
    if exercise is not None:
        step["exercise"] = exercise
        weight = _number(frame, _weight_field)
        if weight is not None and weight > 0:
            step["weight_kg"] = weight
    target, secondary = _targets(index, frame, kind)
    if target is not None:
        step["target"] = target
    if secondary is not None:
        step["secondary_target"] = secondary
    return step


def _kind(index: int, frame: Any) -> str:
    intensity = _text(frame, _intensity_field)
    kind = _KINDS.get(intensity or "")
    if kind is None:
        raise WorkoutFitError(f"FIT step {index} has an unsupported intensity: {intensity}")
    return kind


def _end(index: int, frame: Any, kind: str) -> dict[str, Any]:
    duration = _text(frame, _duration_field)
    value = _number(frame, _duration_value_field)
    if duration == "time" and value is not None:
        return {"type": "time", "seconds": value}
    if duration == "distance" and value is not None:
        if kind in _TIMED_KINDS:
            raise WorkoutFitError(f"FIT step {index} is a {kind} that ends on distance")
        return {"type": "distance", "meters": value}
    if duration == "reps" and value is not None:
        if kind in _TIMED_KINDS:
            raise WorkoutFitError(f"FIT step {index} is a {kind} that ends on repetitions")
        count = int(value)
        if count < 1:
            raise WorkoutFitError(f"FIT step {index} repeats fewer than one repetition")
        return {"type": "reps", "count": count}
    raise WorkoutFitError(f"FIT step {index} has an unsupported duration: {duration}")


def _targets(index: int, frame: Any, kind: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    target = _target(
        index,
        _text(frame, _target_field),
        frame,
        _target_value_field,
        _target_low_field,
        _target_high_field,
    )
    secondary = _target(
        index,
        _text(frame, _secondary_target_field),
        frame,
        _secondary_target_value_field,
        _secondary_low_field,
        _secondary_high_field,
    )
    if (target is not None or secondary is not None) and kind not in _TARGETABLE_KINDS:
        raise WorkoutFitError(f"FIT step {index} is a {kind} with a target")
    if secondary is not None and target is None:
        raise WorkoutFitError(f"FIT step {index} has a secondary target without a target")
    return target, secondary


def _target(
    index: int,
    target_type: str | None,
    frame: Any,
    zone_field: int,
    low_field: int,
    high_field: int,
) -> dict[str, Any] | None:
    if target_type in (None, "open"):
        return None
    zone = _number(frame, zone_field)
    low = _number(frame, low_field)
    high = _number(frame, high_field)
    if target_type == "heart_rate" and zone:
        return {"type": "heart_rate_zone", "zone": int(zone)}
    if target_type == "power" and zone:
        return {"type": "power_zone", "zone": int(zone)}
    if target_type == "heart_rate":
        return _range(index, "heart_rate", _bpm(index, low), _bpm(index, high))
    if target_type == "power":
        return _range(index, "power", _watts(index, low), _watts(index, high))
    if target_type == "cadence":
        return _range(index, "cadence", low, high)
    if target_type == "speed":
        return _range(index, "speed", low, high)
    raise WorkoutFitError(f"FIT step {index} has an unsupported target: {target_type}")


def _range(
    index: int,
    kind: str,
    low: float | None,
    high: float | None,
) -> dict[str, Any]:
    if low is None or high is None:
        raise WorkoutFitError(f"FIT step {index} has an incomplete {kind} target")
    return {"type": kind, "low": low, "high": high}


def _bpm(index: int, value: float | None) -> float:
    if value is None:
        raise WorkoutFitError(f"FIT step {index} has an incomplete heart-rate target")
    if value <= _BPM_OFFSET:
        raise WorkoutFitError(
            f"FIT step {index} targets a percentage of maximum heart rate, not beats per minute"
        )
    return value - _BPM_OFFSET


def _watts(index: int, value: float | None) -> float:
    if value is None:
        raise WorkoutFitError(f"FIT step {index} has an incomplete power target")
    if value <= _WATTS_OFFSET:
        raise WorkoutFitError(
            f"FIT step {index} targets a percentage of threshold power, not watts"
        )
    return value - _WATTS_OFFSET


def _exercise(index: int, frame: Any) -> str | None:
    category = _text(frame, _category_field)
    if category is None:
        return None
    code = _number(frame, _exercise_field)
    if code is None:
        raise WorkoutFitError(f"FIT step {index} names an exercise category without an exercise")
    names = FIELD_TYPES.get(f"{category}_exercise_name")
    exercise = names.enum.get(int(code)) if names is not None and names.enum else None
    if not isinstance(exercise, str):
        raise WorkoutFitError(f"FIT step {index} has an unknown {category} exercise: {int(code)}")
    display = _display_name(category, exercise)
    if display is None:
        raise WorkoutFitError(f"FIT step {index} uses an exercise the catalog does not have: {exercise}")
    return display


def _display_name(category: str, exercise: str) -> str | None:
    global _display_names
    if _display_names is None:
        _display_names = {
            (entry["category"], entry["exercise"]): entry["name"] for entry in exercises.EXERCISES
        }
    return _display_names.get((category.upper(), exercise.upper()))


def _warnings(steps: list[tuple[int, Any]]) -> list[str]:
    with_notes = sum(1 for _, frame in steps if _text(frame, _notes_field) is not None)
    named = sum(1 for _, frame in steps if _text(frame, _step_name_field) is not None)
    warnings: list[str] = []
    if named:
        warnings.append(f"{named} FIT step name(s) are not kept")
    if with_notes:
        warnings.append(f"{with_notes} FIT step note(s) are not kept")
    return warnings


def _step_index(position: int, frame: Any) -> int:
    value = _number(frame, _index_field)
    if value is None:
        return position
    return int(value) & 0x0FFF


def _value(frame: Any, field: int) -> Any:
    found = _field(frame, field)
    return None if found is None else found.value


def _text(frame: Any, field: int) -> str | None:
    value = _value(frame, field)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _number(frame: Any, field: int) -> float | None:
    value = _value(frame, field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _field(frame: Any, field: int) -> Any:
    try:
        return frame.get_field(field)
    except KeyError:
        return None


__all__ = ["WorkoutFitError", "parse_workout_fit"]
