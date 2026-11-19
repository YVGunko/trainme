import base64
import binascii
import hashlib
import json
import logging
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
from app.garmin.device import (
    WorkoutDeviceError,
    WorkoutNotPushed,
    WorkoutRateLimited,
    list_devices,
    parse_device_id,
    push_workout,
    resolve_device,
)
from app.garmin.fit_workout import WorkoutFitError, parse_workout_fit
from app.storage.crypto import EncryptionKeyMissing
from app.storage.db import (
    connect,
    ensure_schema,
    find_workout_import,
    insert_workout_import,
    load_token,
    save_token,
    save_workout_delivery,
)

# Connect displays weightValue as kilograms. The library helper writes grams.
_KILOGRAM = {"unitId": 8, "unitKey": "kilogram", "factor": 1000.0}

logger = logging.getLogger(__name__)

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
# Garmin plans put a power or heart-rate target on warmup, recovery, and
# cooldown steps too, not only on intervals.
_TARGETABLE_TIMED_KINDS = {"warmup", "recovery", "cooldown"}
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


class WorkoutFitFileError(Exception):
    """Raised when an uploaded FIT file cannot be read or is too large.

    ``reason`` is a short code the web layer turns into a sentence, so a caller
    learns why the file was refused instead of reading a generic message.
    """

    def __init__(self, message: str, reason: str = "not_a_workout") -> None:
        super().__init__(message)
        self.reason = reason


# A workout file holds a few hundred bytes. Anything larger is not one.
_MAX_FIT_BYTES = 256 * 1024

# Fields that describe the delivery rather than the Garmin workout body.
_OPTION_KEYS = {"date", "device_id", "push"}


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
    """Upload one workout. A date also puts it on the Garmin calendar.

    Sending the same workout for the same day twice returns the first upload
    instead of making a second one. The key is a hash of the workout plus its
    date, so pressing the button again after a slow response cannot leave two
    copies in the Garmin library.
    """
    _mapping(spec, "workout")
    options = _options(spec)
    payload = build_workout(
        {key: value for key, value in spec.items() if key not in _OPTION_KEYS}
    )

    fingerprint = _fingerprint(payload, options["date"])
    already = _stored_import(fingerprint)
    if already is not None:
        result = {
            "workout_id": already["workout_id"],
            "name": already["name"],
            "stored": False,
        }
        if options["date"] is not None:
            result["date"] = options["date"]
        return result

    client = _open_client()
    workout_id = _workout_id(client.upload_workout(payload))
    _remember_import(fingerprint, workout_id, payload["workoutName"], payload["sportType"]["sportTypeKey"])
    result = {"workout_id": workout_id, "name": payload["workoutName"], "stored": True}
    result.update(_deliver(client, workout_id, payload["sportType"]["sportTypeKey"], options))
    return result


def import_workout_fit(body: dict[str, Any]) -> dict[str, Any]:
    """Read a FIT workout file and send it the same way a described workout goes."""
    options = _options(body)
    payload = _fit_bytes(body.get("content_base64"))
    spec, warnings = _read_fit(payload)

    sha256 = hashlib.sha256(payload).hexdigest()
    stored = _stored_import(sha256)
    client: Any = None
    if stored is None:
        # One login serves the upload, the calendar call, and the device push.
        client = _open_client()
        workout_id = _workout_id(client.upload_workout(build_workout(spec)))
        _remember_import(sha256, workout_id, spec["name"], spec["sport"])
        sport = spec["sport"]
        scheduled = False
    else:
        workout_id = stored["workout_id"]
        sport = stored["sport"]
        scheduled = options["date"] is not None and stored["date"] == options["date"]

    result: dict[str, Any] = {
        "workout_id": workout_id,
        "name": spec["name"],
        "stored": stored is None,
    }
    if warnings:
        result["warnings"] = warnings
    result.update(
        _deliver(client, workout_id, sport, options | {"already_scheduled": scheduled})
    )
    return result


def list_workout_devices() -> dict[str, Any]:
    """Return the Garmin devices a workout can be sent to."""
    client = _open_client()
    return list_devices(client)


def _options(body: dict[str, Any]) -> dict[str, Any]:
    """Read the calendar date, device, and push choice shared by both uploads."""
    day = body.get("date")
    if day is not None and not isinstance(day, str):
        raise WorkoutDateError("Date must be YYYY-MM-DD")
    device_id = parse_device_id(body.get("device_id"))
    if body.get("device_id") is not None and device_id is None:
        raise WorkoutDeviceError("Device id must be a positive integer")
    push = body.get("push", False)
    if not isinstance(push, bool):
        raise WorkoutSpecError("push must be true or false")
    return {
        "date": None if day is None else parse_workout_date(day),
        "device_id": device_id,
        "push": push,
    }


def _deliver(
    client: Any,
    workout_id: int,
    sport: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    """Put the workout on the calendar and, when asked, on a device."""
    day = options["date"]
    result: dict[str, Any] = {}
    if day is not None and not options.get("already_scheduled"):
        active = client if client is not None else _open_client()
        try:
            active.schedule_workout(workout_id, day)
        except Exception as error:
            # The day is not recorded: the calendar call did not happen.
            _remember_delivery(workout_id, None, None)
            raise WorkoutNotScheduled(workout_id) from error
        _remember_delivery(workout_id, day, None)
    if day is not None:
        result["date"] = day
    if options["push"]:
        active = client if client is not None else _open_client()
        result.update(_push(active, workout_id, sport, options["device_id"], day))
    return result


def _push(
    client: Any,
    workout_id: int,
    sport: str,
    device_id: int | None,
    scheduled_day: str | None,
) -> dict[str, Any]:
    try:
        chosen = resolve_device(client, sport, device_id)
    except WorkoutDeviceError as error:
        raise WorkoutNotPushed(workout_id, None) from error
    target = chosen["device_id"]
    try:
        pushed = push_workout(client, workout_id, target)
    except (WorkoutRateLimited, WorkoutDeviceError, WorkoutNotPushed) as error:
        _remember_delivery(workout_id, scheduled_day, None)
        raise WorkoutNotPushed(workout_id, target) from error
    _remember_delivery(workout_id, scheduled_day, target)
    return pushed | {"device_source": chosen["source"]}


def _fit_bytes(value: Any) -> bytes:
    if not isinstance(value, str) or not value:
        raise WorkoutFitFileError("content_base64 is required", "missing")
    try:
        payload = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise WorkoutFitFileError("content_base64 is not base64", "bad_base64") from error
    if not payload:
        raise WorkoutFitFileError("FIT file is empty", "empty")
    if len(payload) > _MAX_FIT_BYTES:
        raise WorkoutFitFileError("FIT file is larger than 256 KB", "too_large")
    return payload


def _read_fit(payload: bytes) -> tuple[dict[str, Any], list[str]]:
    try:
        return parse_workout_fit(payload)
    except WorkoutFitError as error:
        raise WorkoutFitFileError(str(error), error.reason) from error

def _fingerprint(payload: dict[str, Any], day: str | None) -> str:
    """Hash a built workout with its day, to recognise a repeated send.

    The payload is normalised by dumping it with sorted keys, so cosmetic
    differences in the source spec cannot produce a second upload of the same
    session.
    """
    document = {"day": day, "workout": payload}
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _stored_import(sha256: str) -> dict[str, Any] | None:
    with connect() as connection:
        ensure_schema(connection)
        return find_workout_import(connection, sha256)


def _remember_import(sha256: str, workout_id: int, name: str, sport: str) -> None:
    try:
        with connect() as connection:
            insert_workout_import(connection, sha256, workout_id, name, sport)
    except Exception as error:
        # The workout is already in Garmin. Reporting a failure here would make
        # the caller retry and upload a second copy, so only log it.
        logger.warning(
            "Workout %s import row not saved: %s", workout_id, type(error).__name__
        )


def _remember_delivery(workout_id: int, day: str | None, device_id: int | None) -> None:
    try:
        with connect() as connection:
            save_workout_delivery(connection, workout_id, day, device_id)
    except Exception as error:
        # The workout is already in Garmin. A lost delivery row must not turn
        # the answer into a retryable failure that would upload it again.
        logger.warning(
            "Workout %s delivery row not saved: %s", workout_id, type(error).__name__
        )


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
    if target is not None and kind not in {"interval"} | _TARGETABLE_TIMED_KINDS:
        raise WorkoutSpecError("A target belongs on an interval, warmup, recovery, or cooldown step")

    if kind == "warmup":
        built = _timed_step(create_warmup_step, _seconds(end, "warmup"), order, target, secondary)
    elif kind == "cooldown":
        built = _timed_step(create_cooldown_step, _seconds(end, "cooldown"), order, target, secondary)
    elif kind == "recovery":
        built = _timed_step(create_recovery_step, _seconds(end, "recovery"), order, target, secondary)
    elif kind == "rest":
        built = create_strength_rest_step(_seconds(end, "rest"), order)
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


def _timed_step(
    create: Any,
    seconds: float,
    order: int,
    target: Any,
    secondary: Any,
) -> ExecutableStep:
    """Build a warmup, recovery, or cooldown step, with its target when it has one.

    The library helpers only take a bare target type, so a targeted timed step
    is built from the interval helper and then given the timed step type.
    """
    if target is None:
        return create(seconds, order)
    return _retag(_time_interval(seconds, order, target, secondary), create(seconds, order))


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


def _retag(source: ExecutableStep, template: ExecutableStep) -> ExecutableStep:
    """Give a targeted step the step type of a warmup, recovery, or cooldown step."""
    data = source.model_dump(exclude_none=True, mode="json")
    shaped = template.model_dump(exclude_none=True, mode="json")
    data["stepType"] = shaped["stepType"]
    return ExecutableStep.model_validate(data)


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


def _seconds(end: dict[str, Any], kind: str | None = None) -> float:
    if end["type"] != "time":
        # Naming the step is what makes a refusal actionable: a bare "this step
        # ends on time" gives the caller nothing to fix.
        label = f"The {kind} step" if kind else "This step"
        raise WorkoutSpecError(f"{label} must end on time, not on {end['type']}")
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
