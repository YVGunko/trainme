import os
from datetime import date
from typing import Any

from garminconnect import GarminConnectConnectionError, exercises
from garminconnect.workout import (
    BaseWorkout,
    CadenceTarget,
    CustomHeartRateTarget,
    CustomPowerTarget,
    ExecutableStep,
    HeartRateZoneTarget,
    PaceTarget,
    PowerZoneTarget,
    SpeedTarget,
    SportType,
    WorkoutSegment,
    create_cooldown_step,
    create_distance_interval_step,
    create_interval_step,
    create_recovery_step,
    create_repeat_group,
    create_strength_exercise_step,
    create_strength_rest_step,
    create_targeted_distance_interval_step,
    create_targeted_interval_step,
    create_warmup_step,
)
from pydantic import ValidationError

from app.garmin.archive import _login
from app.storage.crypto import EncryptionKeyMissing
from app.storage.db import connect, ensure_schema, load_token, save_token

# Connect displays weightValue as kilograms. The library helper writes grams.
_KILOGRAM = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}

WORKOUT_NAME = "trainme test"

# displayOrder matches the sport id, as it does for the sports this library models.
_SPORTS = {
    "running": {
        "sportTypeId": SportType.RUNNING,
        "sportTypeKey": "running",
        "displayOrder": SportType.RUNNING,
    },
    "cycling": {
        "sportTypeId": SportType.CYCLING,
        "sportTypeKey": "cycling",
        "displayOrder": SportType.CYCLING,
    },
    "strength_training": {
        "sportTypeId": SportType.STRENGTH_TRAINING,
        "sportTypeKey": "strength_training",
        "displayOrder": SportType.STRENGTH_TRAINING,
    },
    "yoga": {
        "sportTypeId": SportType.YOGA,
        "sportTypeKey": "yoga",
        "displayOrder": SportType.YOGA,
    },
    "mobility": {
        "sportTypeId": SportType.MOBILITY,
        "sportTypeKey": "mobility",
        "displayOrder": SportType.MOBILITY,
    },
}

_CATALOG_SPORTS = {"strength_training", "yoga", "mobility"}
_ENDURANCE_SPORTS = {"running", "cycling"}
_TIMED_KINDS = {"warmup", "recovery", "cooldown", "rest"}
_STEP_KEYS = {"kind", "end", "exercise", "weight_kg", "target", "secondary_target"}
_SPEC_KEYS = {"name", "sport", "description", "duration_sec", "blocks"}
_BLOCK_KEYS = {"repeat", "steps"}
_END_KEYS = {
    "time": {"type", "seconds"},
    "distance": {"type", "meters"},
    "reps": {"type", "count"},
}
_RANGE_TARGETS = {"pace", "speed", "power", "heart_rate", "cadence"}
_ZONE_TARGETS = {"power_zone", "heart_rate_zone"}


class WorkoutDateError(Exception):
    """Raised when the requested calendar date is not YYYY-MM-DD."""


class WorkoutSpecError(Exception):
    """Raised when a workout description cannot be sent."""


class WorkoutNotScheduled(Exception):
    """Raised when the template was uploaded and the calendar call failed."""

    def __init__(self, workout_id: int) -> None:
        self.workout_id = workout_id
        super().__init__("Workout uploaded but not scheduled")


def parse_workout_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise WorkoutDateError("Date must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise WorkoutDateError("Date must be YYYY-MM-DD")
    return value


def build_workout(spec: dict[str, Any]) -> dict[str, Any]:
    """Build the Garmin workout JSON for running, cycling, strength, yoga, or mobility."""
    _mapping(spec, "workout")
    _exact_keys(spec, _SPEC_KEYS, "workout")
    sport_name = spec.get("sport")
    sport = _SPORTS.get(sport_name) if isinstance(sport_name, str) else None
    if sport is None:
        raise WorkoutSpecError("Sport must be running, cycling, strength_training, yoga, or mobility")

    name = spec.get("name")
    if not isinstance(name, str) or not name.strip():
        raise WorkoutSpecError("Workout name is required")

    blocks = spec.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise WorkoutSpecError("Workout needs at least one block")

    steps: list[Any] = []
    order = 1
    for block in blocks:
        order = _append_block(steps, block, order, sport_name)

    description = spec.get("description")
    if description is not None and not isinstance(description, str):
        raise WorkoutSpecError("Description must be text")

    workout = BaseWorkout(
        workoutName=name.strip(),
        sportType=dict(sport),
        estimatedDurationInSecs=_duration(spec.get("duration_sec", 0)),
        description=description,
        workoutSegments=[
            WorkoutSegment(segmentOrder=1, sportType=dict(sport), workoutSteps=steps)
        ],
    )
    return workout.to_dict()


def upload_workout(spec: dict[str, Any]) -> dict[str, Any]:
    """Upload one workout. A date also puts it on the Garmin calendar."""
    _mapping(spec, "workout")
    day = spec.get("date")
    scheduled_day = None if day is None else parse_workout_date(day if isinstance(day, str) else "")
    if day is not None and not isinstance(day, str):
        raise WorkoutDateError("Date must be YYYY-MM-DD")
    payload = build_workout({key: value for key, value in spec.items() if key != "date"})

    client = _open_client()
    uploaded = client.upload_workout(payload)
    workout_id = _workout_id(uploaded)
    result = {"workout_id": workout_id, "name": payload["workoutName"]}
    if scheduled_day is None:
        return result
    try:
        client.schedule_workout(workout_id, scheduled_day)
    except Exception as error:
        raise WorkoutNotScheduled(workout_id) from error
    result["date"] = scheduled_day
    return result


def build_test_strength_workout() -> dict[str, Any]:
    return build_workout(_test_strength_spec())


def schedule_test_strength_workout(day: str) -> dict[str, Any]:
    spec = _test_strength_spec()
    spec["date"] = day
    return upload_workout(spec)


def _test_strength_spec() -> dict[str, Any]:
    circuit = (
        ("Goblet Squat", 20, 5.0),
        ("Dumbbell Straight-leg Deadlift", 20, 10.0),
        ("Lateral Dumbbell Step-up", 12, 10.0),
        ("Lateral Dumbbell Step-up", 12, 10.0),
        ("Dumbbell Split Squat", 20, 10.0),
        ("Dumbbell Split Squat", 20, 10.0),
        ("Dumbbell Upright Row", 12, 10.0),
        ("Single-leg Standing Dumbbell Calf Raise", 12, 10.0),
        ("Single-leg Standing Dumbbell Calf Raise", 12, 10.0),
        ("Push-up", 12, None),
    )
    return {
        "name": WORKOUT_NAME,
        "sport": "strength_training",
        "description": "Test strength circuit",
        "blocks": [
            {"steps": [_time_step("warmup", 300)]},
            {
                "repeat": 3,
                "steps": [_reps_step(name, reps, weight) for name, reps, weight in circuit],
            },
            {"steps": [_time_step("cooldown", 600)]},
        ],
    }


def _time_step(kind: str, seconds: float) -> dict[str, Any]:
    return {"kind": kind, "end": {"type": "time", "seconds": seconds}}


def _reps_step(exercise: str, reps: int, weight_kg: float | None) -> dict[str, Any]:
    step = {
        "kind": "interval",
        "end": {"type": "reps", "count": reps},
        "exercise": exercise,
    }
    if weight_kg is not None:
        step["weight_kg"] = weight_kg
    return step


def _append_block(steps: list[Any], block: Any, order: int, sport: str) -> int:
    _mapping(block, "block")
    _exact_keys(block, _BLOCK_KEYS, "block")
    repeat = block.get("repeat", 1)
    repeat = _plain_int(repeat, "repeat")
    if repeat < 1:
        raise WorkoutSpecError("Repeat must be at least 1")
    children_spec = block.get("steps")
    if not isinstance(children_spec, list) or not children_spec:
        raise WorkoutSpecError("Block needs at least one step")

    if repeat == 1:
        for child in children_spec:
            steps.append(_make_step(child, order, sport))
            order += 1
        return order

    group_order = order
    order += 1
    children = []
    for child in children_spec:
        children.append(_make_step(child, order, sport))
        order += 1
    steps.append(create_repeat_group(repeat, children, group_order))
    return order


def _make_step(step: Any, order: int, sport: str) -> ExecutableStep:
    _mapping(step, "step")
    _exact_keys(step, _STEP_KEYS, "step")
    kind = step.get("kind")
    if kind not in {"warmup", "interval", "recovery", "cooldown", "rest"}:
        raise WorkoutSpecError("Step kind must be warmup, interval, recovery, cooldown, or rest")
    end = _end(step.get("end"))
    exercise = step.get("exercise")
    weight = step.get("weight_kg")
    _check_exercise(sport, exercise, weight, end)
    target = step.get("target")
    secondary = step.get("secondary_target")
    if (target is not None or secondary is not None) and sport not in _ENDURANCE_SPORTS:
        raise WorkoutSpecError("Pace, power, heart rate, and cadence targets are for running and cycling")
    if secondary is not None and target is None:
        raise WorkoutSpecError("Secondary target requires a target")
    if target is not None and kind != "interval":
        raise WorkoutSpecError("A target belongs on an interval step")

    if kind == "warmup":
        built = create_warmup_step(_seconds(end), order)
    elif kind == "cooldown":
        built = create_cooldown_step(_seconds(end), order)
    elif kind == "recovery":
        built = create_recovery_step(_seconds(end), order)
    elif kind == "rest":
        built = create_strength_rest_step(_seconds(end), order)
    elif end["type"] == "reps":
        entry = _catalog(exercise)
        count = _plain_int(end["count"], "count")
        if count < 1:
            raise WorkoutSpecError("count must be greater than zero")
        built = create_strength_exercise_step(
            entry["category"],
            order,
            count,
            entry["exercise"],
        )
    elif end["type"] == "distance":
        built = _distance_interval(_positive_number(end["meters"], "meters"), order, target, secondary)
    else:
        built = _time_interval(_positive_number(end["seconds"], "seconds"), order, target, secondary)
    return _apply_catalog(built, exercise if end["type"] != "reps" else None, weight)


def _time_interval(seconds: float, order: int, target: Any, secondary: Any) -> ExecutableStep:
    if target is None:
        return create_interval_step(seconds, order)
    return create_targeted_interval_step(seconds, order, _intensity(target), _optional_intensity(secondary))


def _distance_interval(meters: float, order: int, target: Any, secondary: Any) -> ExecutableStep:
    if target is None:
        return create_distance_interval_step(meters, order)
    return create_targeted_distance_interval_step(
        meters,
        order,
        _intensity(target),
        _optional_intensity(secondary),
    )


def _optional_intensity(target: Any) -> Any:
    if target is None:
        return None
    return _intensity(target)


def _intensity(target: Any) -> Any:
    _mapping(target, "target")
    kind = target.get("type")
    try:
        if kind in _RANGE_TARGETS:
            _exact_keys(target, {"type", "low", "high"}, "target")
            low = _positive_number(target.get("low"), "low")
            high = _positive_number(target.get("high"), "high")
            if kind == "pace":
                return PaceTarget(lower_limit=low, upper_limit=high)
            if kind == "speed":
                return SpeedTarget(lower_limit=low, upper_limit=high)
            if kind == "power":
                return CustomPowerTarget(lower_limit=low, upper_limit=high)
            if kind == "heart_rate":
                return CustomHeartRateTarget(lower_limit=low, upper_limit=high)
            return CadenceTarget(lower_limit=low, upper_limit=high)
        if kind in _ZONE_TARGETS:
            _exact_keys(target, {"type", "zone"}, "target")
            zone = _plain_int(target.get("zone"), "zone")
            if zone < 1:
                raise WorkoutSpecError("Zone must be at least 1")
            if kind == "power_zone":
                return PowerZoneTarget(zone_number=zone)
            return HeartRateZoneTarget(zone_number=zone)
    except ValidationError as error:
        raise WorkoutSpecError("Target lower limit must be less than or equal to the upper limit") from error
    raise WorkoutSpecError(
        "Target must be pace, speed, power, heart_rate, cadence, power_zone, or heart_rate_zone"
    )


def _apply_catalog(
    step: ExecutableStep,
    exercise: str | None,
    weight: Any,
) -> ExecutableStep:
    if exercise is None and weight is None:
        return step
    data = step.model_dump(exclude_none=True, mode="json")
    if exercise is not None:
        entry = _catalog(exercise)
        data["category"] = entry["category"]
        data["exerciseName"] = entry["exercise"]
    if weight is not None:
        data["weightValue"] = _positive_number(weight, "weight_kg")
        data["weightUnit"] = dict(_KILOGRAM)
    return ExecutableStep.model_validate(data)


def _catalog(name: Any) -> dict[str, str]:
    if not isinstance(name, str) or not name.strip():
        raise WorkoutSpecError("Exercise name is required")
    entry = exercises.resolve(name)
    if entry is None:
        raise WorkoutSpecError(f"Unknown exercise: {name}")
    return entry


def _check_exercise(sport: str, exercise: Any, weight: Any, end: dict[str, Any]) -> None:
    if exercise is not None and sport not in _CATALOG_SPORTS:
        raise WorkoutSpecError("Named exercises are for strength, yoga, and mobility")
    if weight is not None and exercise is None:
        raise WorkoutSpecError("Weight requires an exercise")
    if weight is not None and sport not in _CATALOG_SPORTS:
        raise WorkoutSpecError("Weight is for strength, yoga, and mobility")
    if end["type"] == "reps" and sport not in _CATALOG_SPORTS:
        raise WorkoutSpecError("Repetitions are for strength, yoga, and mobility")
    if end["type"] == "reps" and exercise is None:
        raise WorkoutSpecError("A repetition step needs an exercise")
    if end["type"] == "distance" and sport not in _ENDURANCE_SPORTS:
        raise WorkoutSpecError("Distance is for running and cycling")


def _end(value: Any) -> dict[str, Any]:
    _mapping(value, "end")
    kind = value.get("type")
    allowed = _END_KEYS.get(kind)
    if allowed is None:
        raise WorkoutSpecError("End must be time, distance, or reps")
    _exact_keys(value, allowed, "end")
    return value


def _seconds(end: dict[str, Any]) -> float:
    if end["type"] != "time":
        raise WorkoutSpecError("This step ends on time")
    return _positive_number(end["seconds"], "seconds")


def _duration(value: Any) -> int:
    number = _plain_int(value, "duration_sec")
    if number < 0:
        raise WorkoutSpecError("Duration must be zero or greater")
    return number


def _open_client() -> Any:
    key_material = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    if not key_material:
        raise EncryptionKeyMissing
    with connect() as connection:
        ensure_schema(connection)
        saved_token = load_token(connection, key_material)
    client = _login(saved_token)
    with connect() as connection:
        save_token(connection, client.client.dumps(), client.profile_id, key_material)
    return client


def _workout_id(uploaded: Any) -> int:
    if not isinstance(uploaded, dict):
        raise GarminConnectConnectionError("Workout upload did not return an id")
    value = uploaded.get("workoutId")
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GarminConnectConnectionError("Workout upload did not return an id")
    return value


def _mapping(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise WorkoutSpecError(f"{label} must be an object")


def _exact_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise WorkoutSpecError(f"Unknown {label} field: {unknown[0]}")


def _plain_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkoutSpecError(f"{label} must be an integer")
    return value


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkoutSpecError(f"{label} must be a number")
    if value <= 0:
        raise WorkoutSpecError(f"{label} must be greater than zero")
    return float(value)
