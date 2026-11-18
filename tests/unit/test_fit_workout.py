import struct
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fitdecode.utils import compute_crc

from app.garmin.fit_workout import WorkoutFitError, parse_workout_fit
from app.garmin.workout import WorkoutSpecError, build_workout

_FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

_WORKOUT = 26
_WORKOUT_STEP = 27
_FILE_ID = 0

_TIME = 0
_DISTANCE = 1
_REPEAT_UNTIL_STEPS = 6
_REPS = 29

_TARGET_OPEN = 2
_TARGET_HEART_RATE = 1
_TARGET_POWER = 4
_TARGET_CADENCE = 3
_TARGET_SPEED = 0

_INTENSITY = {
    "active": 0,
    "rest": 1,
    "warmup": 2,
    "cooldown": 3,
    "recovery": 4,
    "interval": 5,
    "other": 6,
}

_SPORT = {"running": 1, "cycling": 2, "training": 10}
_SUB_SPORT = {
    "strength_training": 20,
    "yoga": 43,
    "flexibility_training": 19,
}

_GOBLET_SQUAT = ("squat", 37)
_PUSH_UP = ("push_up", 77)
_CHILD_POSE = ("warm_up", 39)
# A FIT exercise code the bundled Garmin catalog does not list.
_UNCATAOGUED = ("banded_exercises", 5)


class _WorkoutFit:
    """Build a FIT workout file message by message."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._next_local = 0
        self._steps = 0

    def file_id(self, kind: int = 5) -> "_WorkoutFit":
        return self._definition_and_message(_FILE_ID, [(0, 1, 0x00)], struct.pack("<B", kind))

    def workout(self, sport: str, name: str, sub_sport: str | None = None) -> "_WorkoutFit":
        fields = [(4, 1, 0x00), (6, 2, 0x84), (254, 2, 0x84)]
        payload = struct.pack("<BHH", _SPORT[sport], 0, 0)
        if sub_sport is not None:
            fields.append((11, 1, 0x00))
            payload += struct.pack("<B", _SUB_SPORT[sub_sport])
        text, size = _fit_text(name)
        fields.append((8, size, 0x07))
        return self._definition_and_message(_WORKOUT, fields, payload + text)

    def time_step(
        self,
        intensity: str,
        seconds: float,
        target: tuple[str, int] | None = None,
        exercise: tuple[str, int] | None = None,
        weight_kg: float | None = None,
    ) -> "_WorkoutFit":
        return self._step(intensity, _TIME, int(seconds * 1000), target, exercise, weight_kg)

    def distance_step(
        self,
        intensity: str,
        meters: float,
        target: tuple[str, int] | None = None,
    ) -> "_WorkoutFit":
        # FIT stores a step distance in centimetres.
        return self._step(intensity, _DISTANCE, int(meters * 100), target, None, None)

    def reps_step(
        self,
        intensity: str,
        count: int,
        exercise: tuple[str, int],
        weight_kg: float | None = None,
    ) -> "_WorkoutFit":
        return self._step(intensity, _REPS, count, None, exercise, weight_kg)

    def repeat(self, first_step: int, count: int, target: tuple[str, int] | None = None) -> "_WorkoutFit":
        return self._step("other", _REPEAT_UNTIL_STEPS, first_step, target, None, None, count)

    def build(self) -> bytes:
        data = b"".join(self._chunks)
        header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
        header += struct.pack("<H", compute_crc(header))
        return header + data + struct.pack("<H", compute_crc(data))

    def _step(
        self,
        intensity: str,
        duration: int,
        value: int,
        target: tuple[str, int] | None,
        exercise: tuple[str, int] | None,
        weight_kg: float | None,
        repeat_count: int = 0,
    ) -> "_WorkoutFit":
        index = self._steps
        self._steps += 1
        fields = [
            (254, 2, 0x84),
            (1, 1, 0x00),
            (2, 4, 0x86),
            (3, 1, 0x00),
            (4, 4, 0x86),
            (5, 4, 0x86),
            (6, 4, 0x86),
            (7, 1, 0x00),
            (10, 1, 0x02),
            (11, 2, 0x84),
            (12, 2, 0x84),
            (13, 1, 0x00),
        ]
        target_type, target_value, low, high = _target_fields(target)
        if repeat_count:
            target_value = repeat_count
        category = 0xFF
        name = 0xFFFF
        weight = 0xFFFF
        unit = 0
        if exercise is not None:
            category, name = _exercise_code(exercise)
            unit = 1
            weight = 0xFFFF if weight_kg is None else int(weight_kg * 100)
        payload = struct.pack(
            "<HBIBIIIBBHHB",
            index,
            duration,
            value,
            target_type,
            target_value,
            low,
            high,
            _INTENSITY[intensity],
            category,
            name,
            weight,
            unit,
        )
        return self._definition_and_message(_WORKOUT_STEP, fields, payload)

    def _definition_and_message(
        self, message: int, fields: list[tuple[int, int, int]], payload: bytes
    ) -> "_WorkoutFit":
        local = self._next_local
        definition = bytearray([0x40 | local, 0, 0])
        definition += struct.pack("<HB", message, len(fields))
        for number, size, base in fields:
            definition += bytes([number, size, base])
        self._chunks.append(bytes(definition) + bytes([local]) + payload)
        self._next_local = (self._next_local + 1) % 16
        return self


def _target_fields(target: tuple[str, int] | None) -> tuple[int, int, int, int]:
    if target is None:
        return _TARGET_OPEN, 0, 0, 0
    kind, value = target
    return {
        "heart_rate": (_TARGET_HEART_RATE, value, 0, 0),
        "power": (_TARGET_POWER, value, 0, 0),
        "cadence": (_TARGET_CADENCE, 0, value, value + 10),
        "speed": (_TARGET_SPEED, 0, value, value + 1),
        "bpm": (_TARGET_HEART_RATE, 0, value + 100, value + 120),
        "watts": (_TARGET_POWER, 0, value + 1000, value + 1050),
        "percent_power": (_TARGET_POWER, 0, value, value + 10),
        "open_with_range": (_TARGET_OPEN, 0, value, value),
    }[kind]


def _exercise_code(exercise: tuple[str, int]) -> tuple[int, int]:
    from fitdecode.profile import FIELD_TYPES

    category = FIELD_TYPES["exercise_category"].enum
    code = {name: number for number, name in category.items()}[exercise[0]]
    return code, exercise[1]


def _fit_text(value: str) -> tuple[bytes, int]:
    encoded = value.encode() + b"\x00"
    return encoded, len(encoded)


class WorkoutFitSportTest(unittest.TestCase):
    def test_running_and_cycling_map_to_the_same_sport(self) -> None:
        for sport in ("running", "cycling"):
            with self.subTest(sport=sport):
                spec, warnings = parse_workout_fit(_running(sport))
                self.assertEqual(spec["sport"], sport)
                self.assertEqual(warnings, [])

    def test_a_training_sub_sport_maps_to_its_workout_sport(self) -> None:
        cases = {
            "strength_training": "strength_training",
            "yoga": "yoga",
            "flexibility_training": "mobility",
        }
        for sub_sport, expected in cases.items():
            with self.subTest(sub_sport=sub_sport):
                payload = (
                    _WorkoutFit()
                    .file_id()
                    .workout("training", "Session", sub_sport=sub_sport)
                    .time_step("warmup", 60)
                    .build()
                )
                spec, _ = parse_workout_fit(payload)
                self.assertEqual(spec["sport"], expected)

    def test_an_unsupported_sport_is_rejected(self) -> None:
        payload = _WorkoutFit().file_id().workout("training", "Swim").time_step("warmup", 60).build()
        with self.assertRaises(WorkoutFitError):
            parse_workout_fit(payload)

    def test_an_activity_file_is_not_a_workout(self) -> None:
        payload = _WorkoutFit().file_id(kind=4).workout("running", "Run").time_step("warmup", 60).build()
        with self.assertRaises(WorkoutFitError) as caught:
            parse_workout_fit(payload)
        self.assertEqual(caught.exception.reason, "activity_file")

    def test_another_fit_file_type_is_named(self) -> None:
        payload = _WorkoutFit().file_id(kind=6).workout("running", "Run").time_step("warmup", 60).build()
        with self.assertRaises(WorkoutFitError) as caught:
            parse_workout_fit(payload)
        self.assertEqual(caught.exception.reason, "other_file")

    def test_a_missing_file_id_is_reported_as_unreadable(self) -> None:
        payload = _WorkoutFit().workout("running", "Run").time_step("warmup", 60).build()
        with self.assertRaises(WorkoutFitError) as caught:
            parse_workout_fit(payload)
        self.assertEqual(caught.exception.reason, "unreadable")

    def test_a_file_without_a_workout_message_is_rejected(self) -> None:
        payload = _WorkoutFit().file_id().time_step("warmup", 60).build()
        with self.assertRaises(WorkoutFitError) as caught:
            parse_workout_fit(payload)
        self.assertEqual(caught.exception.reason, "no_workout_message")

    def test_junk_and_empty_payloads_are_rejected(self) -> None:
        with self.assertRaises(WorkoutFitError) as empty:
            parse_workout_fit(b"")
        self.assertEqual(empty.exception.reason, "empty")
        with self.assertRaises(WorkoutFitError) as junk:
            parse_workout_fit(b"not a fit file")
        self.assertEqual(junk.exception.reason, "unreadable")

    def test_a_truncated_file_is_rejected(self) -> None:
        payload = _running("running")
        for cut in (12, 20, len(payload) - 2):
            with self.subTest(cut=cut):
                with self.assertRaises(WorkoutFitError):
                    parse_workout_fit(payload[:cut])


class WorkoutFitStepTest(unittest.TestCase):
    def test_time_distance_and_rep_steps_keep_their_end_conditions(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("running", "Mix")
            .time_step("warmup", 300)
            .distance_step("interval", 1000)
            .time_step("recovery", 90)
            .time_step("cooldown", 600)
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        steps = [step for block in spec["blocks"] for step in block["steps"]]
        self.assertEqual(
            [(step["kind"], step["end"]["type"]) for step in steps],
            [
                ("warmup", "time"),
                ("interval", "distance"),
                ("recovery", "time"),
                ("cooldown", "time"),
            ],
        )
        self.assertEqual(steps[0]["end"]["seconds"], 300.0)
        self.assertEqual(steps[1]["end"]["meters"], 1000.0)

    def test_reps_step_keeps_the_exercise_and_weight(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("training", "Lift", sub_sport="strength_training")
            .reps_step("interval", 5, _GOBLET_SQUAT, weight_kg=15)
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        step = spec["blocks"][0]["steps"][0]
        self.assertEqual(step["end"], {"type": "reps", "count": 5})
        self.assertEqual(step["exercise"], "Goblet Squat")
        self.assertEqual(step["weight_kg"], 15.0)

    def test_a_repeat_becomes_one_block(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Intervals")
            .time_step("warmup", 600)
            .time_step("interval", 240, target=("power", 3))
            .time_step("recovery", 120)
            .repeat(first_step=1, count=4)
            .time_step("cooldown", 300)
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        self.assertEqual(len(spec["blocks"]), 3)
        self.assertEqual([len(block["steps"]) for block in spec["blocks"]], [1, 2, 1])
        self.assertEqual(spec["blocks"][1]["repeat"], 4)
        self.assertEqual(spec["blocks"][1]["steps"][0]["target"], {"type": "power_zone", "zone": 3})

    def test_a_repeat_without_a_target_on_the_following_step_is_rejected(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Broken")
            .time_step("interval", 240)
            .repeat(first_step=7, count=2)
            .build()
        )
        with self.assertRaises(WorkoutFitError):
            parse_workout_fit(payload)

    def test_a_nested_repeat_is_rejected(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Nested")
            .time_step("interval", 240)
            .repeat(first_step=0, count=2)
            .repeat(first_step=0, count=2)
            .build()
        )
        with self.assertRaises(WorkoutFitError):
            parse_workout_fit(payload)

    def test_an_unsupported_duration_is_rejected(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("running", "Open")
            ._step("interval", 5, 0, None, None, None)  # open duration
            .build()
        )
        with self.assertRaises(WorkoutFitError):
            parse_workout_fit(payload)


class WorkoutFitTargetTest(unittest.TestCase):
    def test_zone_and_custom_targets_are_read(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Targets")
            .time_step("interval", 600, target=("power", 4))
            .time_step("interval", 600, target=("heart_rate", 2))
            .time_step("interval", 600, target=("watts", 200))
            .time_step("interval", 600, target=("bpm", 140))
            .time_step("interval", 600, target=("cadence", 85))
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        targets = [step["target"] for step in spec["blocks"][0]["steps"]]
        self.assertEqual(targets[0], {"type": "power_zone", "zone": 4})
        self.assertEqual(targets[1], {"type": "heart_rate_zone", "zone": 2})
        self.assertEqual(targets[2], {"type": "power", "low": 200.0, "high": 250.0})
        self.assertEqual(targets[3], {"type": "heart_rate", "low": 140.0, "high": 160.0})
        self.assertEqual(targets[4], {"type": "cadence", "low": 85.0, "high": 95.0})

    def test_a_percent_of_threshold_power_is_rejected_instead_of_guessed(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Percent")
            .time_step("interval", 600, target=("percent_power", 90))
            .build()
        )
        with self.assertRaises(WorkoutFitError):
            parse_workout_fit(payload)

    def test_a_target_on_a_warmup_is_kept(self) -> None:
        # Garmin writes power targets on warmup steps, so this must parse.
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Warm")
            .time_step("warmup", 600, target=("power", 2))
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        step = spec["blocks"][0]["steps"][0]
        self.assertEqual(step["kind"], "warmup")
        self.assertEqual(step["target"], {"type": "power_zone", "zone": 2})

    def test_a_target_on_a_rest_step_is_rejected(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("training", "Rest", sub_sport="strength_training")
            .time_step("rest", 60, target=("heart_rate", 2))
            .build()
        )
        with self.assertRaises(WorkoutFitError):
            parse_workout_fit(payload)

    def test_an_exercise_outside_the_catalog_is_rejected(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("training", "Unknown", sub_sport="strength_training")
            .reps_step("interval", 5, _UNCATAOGUED)
            .build()
        )
        with self.assertRaises(WorkoutFitError):
            parse_workout_fit(payload)


class WorkoutFitValueWarningTest(unittest.TestCase):
    """A file whose numbers are wrong is readable, but must not pass silently."""

    def test_a_step_shorter_than_a_second_is_reported(self) -> None:
        # A generator that writes minutes into the millisecond field gives 0.24 s.
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Broken units")
            .time_step("warmup", 0.24)
            .time_step("interval", 0.18)
            .build()
        )
        _, warnings = parse_workout_fit(payload)
        short = [w for w in warnings if w["code"] == "short_steps"]
        self.assertEqual(len(short), 1)
        self.assertEqual(short[0]["count"], 2)
        self.assertEqual(short[0]["smallest"], 0.18)

    def test_a_workout_under_a_minute_is_reported(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Too short")
            .time_step("warmup", 0.24)
            .build()
        )
        _, warnings = parse_workout_fit(payload)
        short = [w for w in warnings if w["code"] == "short_workout"]
        self.assertEqual(len(short), 1)
        self.assertAlmostEqual(short[0]["total_seconds"], 0.24)

    def test_a_repeat_counts_toward_the_total(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Repeated")
            .time_step("interval", 30)
            .repeat(first_step=0, count=3)
            .build()
        )
        _, warnings = parse_workout_fit(payload)
        self.assertFalse(any(w["code"] == "short_workout" for w in warnings))

    def test_a_distance_step_shorter_than_a_meter_is_reported(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("running", "Broken distance")
            .distance_step("interval", 0.5)
            .build()
        )
        _, warnings = parse_workout_fit(payload)
        short = [w for w in warnings if w["code"] == "short_distance_steps"]
        self.assertEqual(len(short), 1)
        self.assertEqual(short[0]["smallest"], 0.5)

    def test_a_normal_workout_has_no_value_warning(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("cycling", "Normal")
            .time_step("warmup", 600)
            .time_step("interval", 1200)
            .time_step("cooldown", 300)
            .build()
        )
        _, warnings = parse_workout_fit(payload)
        self.assertEqual(warnings, [])


class RealGarminWorkoutFitTest(unittest.TestCase):
    """Parse the file a Garmin Edge 840 wrote, not a fixture we invented."""

    def _payload(self) -> bytes:
        path = Path(__file__).resolve().parents[1] / "fixtures" / "adaptive-endurance-ride.fit"
        return path.read_bytes()

    def test_a_real_workout_file_is_read(self) -> None:
        spec, warnings = parse_workout_fit(self._payload())
        self.assertEqual(spec["sport"], "cycling")
        self.assertEqual(spec["name"], "Adaptive Endurance Ride")
        self.assertEqual(len(spec["blocks"]), 1)
        steps = spec["blocks"][0]["steps"]
        self.assertEqual(len(steps), 16)
        # The file is sound: only its step names and notes are lost.
        self.assertEqual(
            warnings,
            [
                {"code": "step_names_dropped", "count": 16},
                {"code": "notes_dropped", "count": 16},
            ],
        )

    def test_a_real_file_raises_no_numeric_warning(self) -> None:
        _, warnings = parse_workout_fit(self._payload())
        self.assertFalse(any(w["code"].startswith("short_") for w in warnings))

    def test_a_warmup_step_keeps_its_power_zone(self) -> None:
        # Garmin puts a power target on the warmup, which used to be rejected.
        spec, _ = parse_workout_fit(self._payload())
        first = spec["blocks"][0]["steps"][0]
        self.assertEqual(first["kind"], "warmup")
        self.assertEqual(first["end"], {"type": "time", "seconds": 240.0})
        self.assertEqual(first["target"], {"type": "power_zone", "zone": 1})
        self.assertEqual(first["secondary_target"], {"type": "cadence", "low": 85.0, "high": 90.0})

    def test_a_real_file_becomes_a_garmin_workout(self) -> None:
        spec, _ = parse_workout_fit(self._payload())
        built = build_workout(spec)
        steps = built["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(built["sportType"]["sportTypeKey"], "cycling")
        self.assertEqual(len(steps), 16)
        warmup = steps[0]
        self.assertEqual(warmup["stepType"]["stepTypeKey"], "warmup")
        self.assertEqual(warmup["endConditionValue"], 240.0)
        self.assertEqual(warmup["targetType"]["workoutTargetTypeKey"], "power.zone")
        self.assertEqual(warmup["zoneNumber"], 1)
        self.assertEqual(warmup["secondaryTargetType"]["workoutTargetTypeKey"], "cadence")
        self.assertEqual(warmup["secondaryTargetValueOne"], 85.0)
        self.assertEqual(warmup["secondaryTargetValueTwo"], 90.0)

    def test_every_step_is_one_garmin_step(self) -> None:
        spec, _ = parse_workout_fit(self._payload())
        steps = build_workout(spec)["workoutSegments"][0]["workoutSteps"]
        orders = [step["stepOrder"] for step in steps]
        self.assertEqual(orders, list(range(1, 17)))
        self.assertTrue(all(step["endCondition"]["conditionTypeKey"] == "time" for step in steps))


class WorkoutFitToGarminTest(unittest.TestCase):
    def test_a_parsed_workout_passes_the_existing_checks(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("training", "Circuit", sub_sport="strength_training")
            .time_step("warmup", 300)
            .reps_step("interval", 20, _GOBLET_SQUAT, weight_kg=5)
            .repeat(first_step=1, count=3)
            .time_step("cooldown", 600)
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        built = build_workout(spec)
        steps = built["workoutSegments"][0]["workoutSteps"]
        self.assertEqual(built["sportType"]["sportTypeKey"], "strength_training")
        self.assertEqual(steps[0]["stepType"]["stepTypeKey"], "warmup")
        self.assertEqual(steps[1]["numberOfIterations"], 3)
        self.assertEqual(steps[1]["workoutSteps"][0]["exerciseName"], "GOBLET_SQUAT")
        self.assertEqual(steps[1]["workoutSteps"][0]["weightValue"], 5.0)
        self.assertEqual(steps[2]["stepType"]["stepTypeKey"], "cooldown")

    def test_a_yoga_pose_keeps_its_catalog_name(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("training", "Hips", sub_sport="yoga")
            .time_step("interval", 45, exercise=_CHILD_POSE)
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        built = build_workout(spec)
        step = built["workoutSegments"][0]["workoutSteps"][0]
        self.assertEqual(step["exerciseName"], "STRETCH_CHILDS_POSE")

    def test_a_time_step_named_only_in_the_file_still_sends(self) -> None:
        payload = (
            _WorkoutFit()
            .file_id()
            .workout("running", "Named")
            .time_step("interval", 60, exercise=_PUSH_UP)
            .build()
        )
        spec, _ = parse_workout_fit(payload)
        with self.assertRaises(WorkoutSpecError):
            build_workout(spec)


def _running(sport: str) -> bytes:
    return (
        _WorkoutFit()
        .file_id()
        .workout(sport, "Easy")
        .time_step("warmup", 300)
        .time_step("cooldown", 300)
        .build()
    )
