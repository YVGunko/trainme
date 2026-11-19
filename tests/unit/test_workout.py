import base64
import os
import struct
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from fitdecode.utils import compute_crc
from garminconnect import GarminConnectConnectionError

from app.garmin.device import WorkoutDeviceError, WorkoutNotPushed, WorkoutRateLimited
from app.garmin.workout import (
    WorkoutDateError,
    WorkoutFitFileError,
    WorkoutNotScheduled,
    WorkoutSpecError,
    build_test_strength_workout,
    build_workout,
    import_workout_fit,
    parse_workout_date,
    schedule_test_strength_workout,
    upload_workout,
)
from app.main import app


class StrengthWorkoutPayloadTest(unittest.TestCase):
    def test_circuit_is_three_rounds_with_kilogram_targets(self) -> None:
        payload = build_test_strength_workout()
        segment = payload["workoutSegments"][0]
        steps = segment["workoutSteps"]

        self.assertEqual(payload["workoutName"], "trainme test")
        self.assertEqual(payload["sportType"]["sportTypeKey"], "strength_training")
        self.assertEqual(steps[0]["endConditionValue"], 300.0)
        self.assertEqual(steps[0]["stepType"]["stepTypeKey"], "warmup")
        self.assertEqual(steps[1]["numberOfIterations"], 3)
        self.assertEqual(steps[2]["endConditionValue"], 600.0)
        self.assertEqual(steps[2]["stepType"]["stepTypeKey"], "cooldown")

        exercises = steps[1]["workoutSteps"]
        self.assertEqual(
            [step["exerciseName"] for step in exercises],
            [
                "GOBLET_SQUAT",
                "DUMBBELL_STRAIGHT_LEG_DEADLIFT",
                "LATERAL_DUMBBELL_STEP_UP",
                "LATERAL_DUMBBELL_STEP_UP",
                "DUMBBELL_SPLIT_SQUAT",
                "DUMBBELL_SPLIT_SQUAT",
                "DUMBBELL_UPRIGHT_ROW",
                "SINGLE_LEG_STANDING_DUMBBELL_CALF_RAISE",
                "SINGLE_LEG_STANDING_DUMBBELL_CALF_RAISE",
                "PUSH_UP",
            ],
        )
        self.assertEqual(exercises[0]["weightValue"], 5.0)
        self.assertEqual(exercises[1]["weightValue"], 10.0)
        self.assertEqual(exercises[2]["weightValue"], 10.0)
        self.assertNotIn("weightValue", exercises[-1])
        self.assertTrue(all(step["weightUnit"]["unitKey"] == "kilogram" for step in exercises[:-1]))
        self.assertNotIn(5000.0, [step.get("weightValue") for step in exercises])
        self.assertNotIn(10000.0, [step.get("weightValue") for step in exercises])

        orders = [steps[0]["stepOrder"], steps[1]["stepOrder"], steps[2]["stepOrder"]]
        orders.extend(step["stepOrder"] for step in exercises)
        self.assertEqual(len(orders), len(set(orders)))


class GeneralWorkoutTest(unittest.TestCase):
    def test_running_interval_carries_a_pace_target(self) -> None:
        payload = build_workout(
            {
                "name": "Easy run",
                "sport": "running",
                "blocks": [
                    {
                        "steps": [
                            {
                                "kind": "interval",
                                "end": {"type": "distance", "meters": 1000},
                                "target": {"type": "pace", "low": 3.0, "high": 3.4},
                            }
                        ]
                    }
                ],
            }
        )
        step = payload["workoutSegments"][0]["workoutSteps"][0]
        self.assertEqual(payload["sportType"], {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1})
        self.assertEqual(step["endCondition"]["conditionTypeKey"], "distance")
        self.assertEqual(step["targetType"]["workoutTargetTypeKey"], "pace.zone")
        self.assertNotIn("category", step)

    def test_cycling_interval_carries_power_and_cadence(self) -> None:
        payload = build_workout(
            {
                "name": "Sweet spot",
                "sport": "cycling",
                "blocks": [
                    {
                        "repeat": 2,
                        "steps": [
                            {
                                "kind": "interval",
                                "end": {"type": "time", "seconds": 600},
                                "target": {"type": "power", "low": 200, "high": 250},
                                "secondary_target": {"type": "cadence", "low": 85, "high": 95},
                            }
                        ],
                    }
                ],
            }
        )
        group = payload["workoutSegments"][0]["workoutSteps"][0]
        step = group["workoutSteps"][0]
        self.assertEqual(payload["sportType"]["sportTypeKey"], "cycling")
        self.assertEqual(group["numberOfIterations"], 2)
        self.assertEqual(step["targetType"]["workoutTargetTypeKey"], "power.zone")
        self.assertEqual(step["targetValueOne"], 200.0)
        self.assertEqual(step["secondaryTargetType"]["workoutTargetTypeKey"], "cadence")

    def test_yoga_and_mobility_name_a_catalog_stretch(self) -> None:
        yoga = build_workout(
            {
                "name": "Hips",
                "sport": "yoga",
                "blocks": [
                    {
                        "steps": [
                            {
                                "kind": "interval",
                                "end": {"type": "time", "seconds": 45},
                                "exercise": "Child's Pose Stretch",
                            }
                        ]
                    }
                ],
            }
        )
        mobility = build_workout(
            {
                "name": "Spine",
                "sport": "mobility",
                "blocks": [
                    {
                        "steps": [
                            {
                                "kind": "interval",
                                "end": {"type": "reps", "count": 8},
                                "exercise": "Cobra Stretch",
                            }
                        ]
                    }
                ],
            }
        )
        yoga_step = yoga["workoutSegments"][0]["workoutSteps"][0]
        mobility_step = mobility["workoutSegments"][0]["workoutSteps"][0]
        self.assertEqual(yoga["sportType"], {"sportTypeId": 7, "sportTypeKey": "yoga", "displayOrder": 7})
        self.assertEqual(yoga_step["category"], "WARM_UP")
        self.assertEqual(yoga_step["exerciseName"], "STRETCH_CHILDS_POSE")
        self.assertEqual(yoga_step["endCondition"]["conditionTypeKey"], "time")
        self.assertEqual(mobility["sportType"]["sportTypeId"], 11)
        self.assertEqual(mobility_step["category"], "WARM_UP")
        self.assertEqual(mobility_step["exerciseName"], "STRETCH_COBRA")
        self.assertEqual(mobility_step["endCondition"]["conditionTypeKey"], "reps")

    def test_strength_weight_stays_in_kilograms(self) -> None:
        payload = build_workout(
            {
                "name": "Squat",
                "sport": "strength_training",
                "blocks": [
                    {
                        "steps": [
                            {
                                "kind": "interval",
                                "end": {"type": "reps", "count": 5},
                                "exercise": "Goblet Squat",
                                "weight_kg": 10,
                            }
                        ]
                    }
                ],
            }
        )
        step = payload["workoutSegments"][0]["workoutSteps"][0]
        self.assertEqual(step["weightValue"], 10.0)
        self.assertEqual(step["weightUnit"]["unitKey"], "kilogram")

    def test_a_reps_warmup_names_the_step_that_is_wrong(self) -> None:
        # A refusal has to say which step to fix, not just that something is off.
        with self.assertRaises(WorkoutSpecError) as caught:
            build_workout(
                {
                    "name": "Strength",
                    "sport": "strength_training",
                    "blocks": [
                        {
                            "steps": [
                                {
                                    "kind": "warmup",
                                    "end": {"type": "reps", "count": 10},
                                    "exercise": "Goblet Squat",
                                }
                            ]
                        }
                    ],
                }
            )
        self.assertIn("warmup", str(caught.exception))
        self.assertIn("reps", str(caught.exception))

    def test_rejects_a_named_exercise_on_a_run(self) -> None:
        with self.assertRaises(WorkoutSpecError):
            build_workout(
                {
                    "name": "Run",
                    "sport": "running",
                    "blocks": [
                        {
                            "steps": [
                                {
                                    "kind": "interval",
                                    "end": {"type": "time", "seconds": 60},
                                    "exercise": "Push-up",
                                }
                            ]
                        }
                    ],
                }
            )

    def test_rejects_an_unknown_stretch_and_a_pace_target_on_yoga(self) -> None:
        with self.assertRaises(WorkoutSpecError):
            build_workout(
                {
                    "name": "Yoga",
                    "sport": "yoga",
                    "blocks": [
                        {
                            "steps": [
                                {
                                    "kind": "interval",
                                    "end": {"type": "time", "seconds": 30},
                                    "exercise": "Definitely Not A Pose",
                                }
                            ]
                        }
                    ],
                }
            )
        with self.assertRaises(WorkoutSpecError):
            build_workout(
                {
                    "name": "Yoga",
                    "sport": "yoga",
                    "blocks": [
                        {
                            "steps": [
                                {
                                    "kind": "interval",
                                    "end": {"type": "time", "seconds": 30},
                                    "target": {"type": "pace", "low": 3, "high": 4},
                                }
                            ]
                        }
                    ],
                }
            )


class UploadWorkoutTest(unittest.TestCase):
    def test_uploads_without_scheduling_when_no_date_is_given(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 9}
        spec = {
            "name": "Hips",
            "sport": "yoga",
            "blocks": [
                {
                    "steps": [
                        {
                            "kind": "interval",
                            "end": {"type": "time", "seconds": 45},
                            "exercise": "Pigeon Pose Stretch",
                        }
                    ]
                }
            ],
        }
        with _patched_client(client):
            result = upload_workout(spec)
        sent = client.upload_workout.call_args.args[0]
        self.assertEqual(sent["sportType"]["sportTypeKey"], "yoga")
        self.assertEqual(sent["workoutSegments"][0]["workoutSteps"][0]["exerciseName"], "STRETCH_PIGEON_POSE")
        client.schedule_workout.assert_not_called()
        self.assertEqual(result, {"workout_id": 9, "name": "Hips", "stored": True})


class UploadWithPushTest(unittest.TestCase):
    def test_a_pushed_workout_reports_the_device(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}
        client.push_workout_to_device.return_value = {}
        spec = {
            "name": "Sweet spot",
            "sport": "cycling",
            "push": True,
            "blocks": [
                {
                    "steps": [
                        {"kind": "interval", "end": {"type": "time", "seconds": 600}},
                    ]
                }
            ],
        }
        with _patched_client(client):
            with patch("app.garmin.device.sport_device_id", return_value=111):
                result = upload_workout(spec)
        client.push_workout_to_device.assert_called_once_with(55, 111)
        self.assertEqual(
            result,
            {
                "workout_id": 55,
                "name": "Sweet spot",
                "device_id": 111,
                "pushed": True,
                "device_source": "sport",
                "stored": True,
            },
        )

    def test_a_rate_limited_push_keeps_the_uploaded_id(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}
        client.push_workout_to_device.side_effect = GarminConnectConnectionError(
            "API Error 429 - slow down"
        )
        spec = {
            "name": "Sweet spot",
            "sport": "cycling",
            "push": True,
            "blocks": [
                {"steps": [{"kind": "interval", "end": {"type": "time", "seconds": 600}}]}
            ],
        }
        with _patched_client(client):
            with patch("app.garmin.device.sport_device_id", return_value=111):
                with self.assertRaises(WorkoutNotPushed) as caught:
                    upload_workout(spec)
        self.assertEqual(caught.exception.workout_id, 55)
        self.assertIsInstance(caught.exception.__cause__, WorkoutRateLimited)

    def test_no_device_leaves_the_workout_uploaded(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}
        spec = {
            "name": "Hips",
            "sport": "yoga",
            "push": True,
            "blocks": [
                {"steps": [{"kind": "interval", "end": {"type": "time", "seconds": 45}}]}
            ],
        }
        with _patched_client(client):
            with patch("app.garmin.device.primary_device_id", return_value=None):
                with patch("app.garmin.device.last_used_device_id", return_value=None):
                    with self.assertRaises(WorkoutNotPushed) as caught:
                        upload_workout(spec)
        self.assertEqual(caught.exception.workout_id, 55)
        self.assertIsNone(caught.exception.device_id)

    def test_a_chosen_device_is_used_as_given(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}
        spec = {
            "name": "Hips",
            "sport": "yoga",
            "push": True,
            "device_id": 987,
            "blocks": [
                {"steps": [{"kind": "interval", "end": {"type": "time", "seconds": 45}}]}
            ],
        }
        with _patched_client(client):
            result = upload_workout(spec)
        client.push_workout_to_device.assert_called_once_with(55, 987)
        self.assertEqual(result["device_source"], "requested")

    def test_a_failed_calendar_call_does_not_record_the_day(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}
        client.schedule_workout.side_effect = RuntimeError("calendar down")
        spec = {
            "name": "Hips",
            "sport": "yoga",
            "date": "2026-11-18",
            "blocks": [
                {"steps": [{"kind": "interval", "end": {"type": "time", "seconds": 45}}]}
            ],
        }
        with _patched_client(client):
            with patch("app.garmin.workout.save_workout_delivery") as save_delivery:
                with self.assertRaises(WorkoutNotScheduled):
                    upload_workout(spec)
        self.assertEqual(save_delivery.call_args.args[2], None)

    def test_a_bad_device_id_is_rejected_before_upload(self) -> None:
        client = MagicMock()
        spec = {
            "name": "Hips",
            "sport": "yoga",
            "push": True,
            "device_id": "abc",
            "blocks": [
                {"steps": [{"kind": "interval", "end": {"type": "time", "seconds": 45}}]}
            ],
        }
        with _patched_client(client):
            with self.assertRaises(WorkoutDeviceError):
                upload_workout(spec)
        client.upload_workout.assert_not_called()


class ImportFitWorkoutTest(unittest.TestCase):
    def test_a_file_with_wrong_units_still_uploads_and_reports_it(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 77}
        with _patched_client(client):
            with patch("app.garmin.workout.find_workout_import", return_value=None):
                with patch("app.garmin.workout.insert_workout_import"):
                    result = import_workout_fit({"content_base64": _base64(_broken_units_fit())})
        codes = {warning["code"] for warning in result["warnings"]}
        self.assertIn("short_steps", codes)
        self.assertIn("short_workout", codes)
        self.assertEqual(result["workout_id"], 77)

    def test_a_sound_file_reports_no_value_warning(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 77}
        with _patched_client(client):
            with patch("app.garmin.workout.find_workout_import", return_value=None):
                with patch("app.garmin.workout.insert_workout_import"):
                    result = import_workout_fit({"content_base64": _base64(_running_fit())})
        self.assertNotIn("warnings", result)

    def test_a_new_file_is_uploaded_once_and_remembered(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 77}
        payload = _running_fit()
        with _patched_client(client):
            with patch("app.garmin.workout.find_workout_import", return_value=None):
                with patch("app.garmin.workout.insert_workout_import") as remember:
                    result = import_workout_fit({"content_base64": _base64(payload)})
        client.upload_workout.assert_called_once()
        remember.assert_called_once()
        self.assertEqual(result["workout_id"], 77)
        self.assertTrue(result["stored"])
        self.assertEqual(result["name"], "Easy")

    def test_the_same_file_again_does_not_upload(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        payload = _running_fit()
        stored = {"workout_id": 77, "name": "Easy", "sport": "running", "date": None, "pushed": False}
        with _patched_client(client):
            with patch("app.garmin.workout.find_workout_import", return_value=stored):
                result = import_workout_fit({"content_base64": _base64(payload)})
        client.upload_workout.assert_not_called()
        self.assertFalse(result["stored"])
        self.assertEqual(result["workout_id"], 77)

    def test_a_stored_file_can_still_be_scheduled_and_pushed(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.push_workout_to_device.return_value = {}
        payload = _running_fit()
        stored = {"workout_id": 77, "name": "Easy", "sport": "running", "date": None, "pushed": False}
        with _patched_client(client):
            with patch("app.garmin.workout.find_workout_import", return_value=stored):
                with patch("app.garmin.device.sport_device_id", return_value=222):
                    result = import_workout_fit(
                        {
                            "content_base64": _base64(payload),
                            "date": "2026-11-18",
                            "push": True,
                        }
                    )
        client.upload_workout.assert_not_called()
        client.schedule_workout.assert_called_once_with(77, "2026-11-18")
        client.push_workout_to_device.assert_called_once_with(77, 222)
        self.assertEqual(
            result,
            {
                "workout_id": 77,
                "name": "Easy",
                "stored": False,
                "date": "2026-11-18",
                "device_id": 222,
                "pushed": True,
                "device_source": "sport",
            },
        )

    def test_a_failed_import_row_does_not_fail_the_upload(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 77}
        payload = _running_fit()
        with _patched_client(client):
            with patch("app.garmin.workout.find_workout_import", return_value=None):
                with patch("app.garmin.workout.insert_workout_import", side_effect=RuntimeError("db")):
                    result = import_workout_fit({"content_base64": _base64(payload)})
        self.assertEqual(result["workout_id"], 77)

    def test_a_missing_database_stops_the_import_before_upload(self) -> None:
        from app.storage.db import DatabaseNotConfigured

        with patch("app.garmin.workout.connect", side_effect=DatabaseNotConfigured()):
            with patch("app.garmin.workout._open_client") as open_client:
                with self.assertRaises(DatabaseNotConfigured):
                    import_workout_fit({"content_base64": _base64(_running_fit())})
        open_client.assert_not_called()

    def test_a_bad_file_is_rejected_before_login(self) -> None:
        with patch("app.garmin.workout._open_client") as open_client:
            with self.assertRaises(WorkoutFitFileError) as caught:
                import_workout_fit({"content_base64": _base64(b"not a fit file")})
        open_client.assert_not_called()
        self.assertEqual(caught.exception.reason, "unreadable")

    def test_an_activity_file_says_so(self) -> None:
        with patch("app.garmin.workout._open_client") as open_client:
            with self.assertRaises(WorkoutFitFileError) as caught:
                import_workout_fit({"content_base64": _base64(_activity_fit())})
        open_client.assert_not_called()
        self.assertEqual(caught.exception.reason, "activity_file")

    def test_a_file_above_the_size_limit_is_rejected(self) -> None:
        oversized = b"\x00" * (256 * 1024 + 1)
        with patch("app.garmin.workout._open_client") as open_client:
            with self.assertRaises(WorkoutFitFileError) as caught:
                import_workout_fit({"content_base64": _base64(oversized)})
        open_client.assert_not_called()
        self.assertEqual(caught.exception.reason, "too_large")

    def test_a_missing_file_is_rejected(self) -> None:
        for body in ({}, {"content_base64": ""}, {"content_base64": 5}):
            with self.subTest(body=body):
                with self.assertRaises(WorkoutFitFileError) as caught:
                    import_workout_fit(body)
                self.assertEqual(caught.exception.reason, "missing")

    def test_content_that_is_not_base64_says_so(self) -> None:
        with self.assertRaises(WorkoutFitFileError) as caught:
            import_workout_fit({"content_base64": "***"})
        self.assertEqual(caught.exception.reason, "bad_base64")


class UploadDeduplicationTest(unittest.TestCase):
    def _spec(self) -> dict:
        return {
            "name": "Hips",
            "sport": "yoga",
            "blocks": [
                {"steps": [{"kind": "interval", "end": {"type": "time", "seconds": 45}}]}
            ],
        }

    def test_the_same_workout_for_the_same_day_is_not_uploaded_twice(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        stored = {"workout_id": 42, "name": "Hips", "sport": "yoga", "date": None}
        with _patched_client(client):
            with patch("app.garmin.workout.find_workout_import", return_value=stored):
                result = upload_workout(self._spec())
        client.upload_workout.assert_not_called()
        self.assertEqual(result["workout_id"], 42)
        self.assertFalse(result["stored"])

    def test_different_workouts_are_both_uploaded(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 9}
        first = self._spec()
        second = {**self._spec(), "name": "Other hips"}
        with _patched_client(client):
            upload_workout(first)
            upload_workout(second)
        self.assertEqual(client.upload_workout.call_count, 2)

    def test_the_same_workout_for_a_different_day_is_uploaded(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 9}
        with _patched_client(client):
            upload_workout({**self._spec(), "date": "2026-11-19"})
            upload_workout({**self._spec(), "date": "2026-11-20"})
        self.assertEqual(client.upload_workout.call_count, 2)


class WorkoutDateTest(unittest.TestCase):
    def test_accepts_a_calendar_date(self) -> None:
        self.assertEqual(parse_workout_date("2026-10-13"), "2026-10-13")

    def test_rejects_a_missing_calendar_date(self) -> None:
        with self.assertRaises(WorkoutDateError):
            parse_workout_date("13.10.2026")


class ScheduleStrengthWorkoutTest(unittest.TestCase):
    def test_uploads_then_schedules_the_returned_id(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}

        with _patched_client(client):
            result = schedule_test_strength_workout("2026-10-13")

        uploaded = client.upload_workout.call_args.args[0]
        self.assertEqual(uploaded["workoutSegments"][0]["workoutSteps"][1]["workoutSteps"][0]["weightValue"], 5.0)
        client.schedule_workout.assert_called_once_with(55, "2026-10-13")
        self.assertEqual(
            result,
            {"workout_id": 55, "date": "2026-10-13", "name": "trainme test", "stored": True},
        )

    def test_keeps_the_id_when_scheduling_fails(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}
        client.schedule_workout.side_effect = RuntimeError("calendar down")

        with _patched_client(client):
            with self.assertRaises(WorkoutNotScheduled) as caught:
                schedule_test_strength_workout("2026-10-13")

        self.assertEqual(caught.exception.workout_id, 55)


class StrengthWorkoutRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/workouts/strength-test", json={"date": "2026-10-13"})
        self.assertEqual(response.status_code, 401)

    def test_rejects_a_bad_date(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/workouts/strength-test",
                json={"date": "today"},
                headers={"Authorization": "Bearer expected"},
            )
        self.assertEqual(response.status_code, 400)

    def test_returns_the_scheduled_id(self) -> None:
        client = TestClient(app)
        summary = {"workout_id": 55, "date": "2026-10-13", "name": "trainme test"}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.schedule_test_strength_workout", return_value=summary):
                response = client.post(
                    "/workouts/strength-test",
                    json={"date": "2026-10-13"},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)
        self.assertNotIn("di_token", response.text)


class _FakeConnection:
    def __enter__(self) -> MagicMock:
        return MagicMock()

    def __exit__(self, *_: Any) -> bool:
        return False


def _patched_client(client: Any) -> Any:
    """Patch the login and token calls so a workout test needs no Garmin account."""
    stack = _ExitStack()
    stack.enter_context(patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key"}))
    stack.enter_context(patch("app.garmin.workout.connect", return_value=_FakeConnection()))
    stack.enter_context(patch("app.garmin.workout.load_token", return_value="saved"))
    stack.enter_context(patch("app.garmin.workout._login", return_value=client))
    stack.enter_context(patch("app.garmin.workout.save_token"))
    stack.enter_context(patch("app.garmin.workout.ensure_schema"))
    stack.enter_context(patch("app.garmin.workout.save_workout_delivery"))
    # The upload is keyed on a fingerprint, so a test must not depend on a
    # previous upload having been stored.
    stack.enter_context(patch("app.garmin.workout.find_workout_import", return_value=None))
    stack.enter_context(patch("app.garmin.workout.insert_workout_import"))
    return stack


class _ExitStack:
    def __init__(self) -> None:
        self._patchers: list[Any] = []

    def enter_context(self, patcher: Any) -> Any:
        self._patchers.append(patcher)
        return patcher.__enter__()

    def __enter__(self) -> "_ExitStack":
        return self

    def __exit__(self, *_: Any) -> bool:
        for patcher in reversed(self._patchers):
            patcher.__exit__(None, None, None)
        return False


def _running_fit() -> bytes:
    data = _definition(0, 0, [(0, 1, 0x00)]) + b"\x00" + struct.pack("<B", 5)
    name = b"Easy\x00"
    data += _definition(1, 26, [(4, 1, 0x00), (8, len(name), 0x07)])
    data += b"\x01" + struct.pack("<B", 1) + name
    data += _definition(2, 27, [(254, 2, 0x84), (1, 1, 0x00), (2, 4, 0x86), (3, 1, 0x00), (7, 1, 0x00)])
    data += b"\x02" + struct.pack("<H", 0) + struct.pack("<BIBB", 0, 300000, 2, 2)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


def _definition(local: int, message: int, fields: list[tuple[int, int, int]]) -> bytes:
    payload = bytearray([0x40 | local, 0, 0])
    payload += struct.pack("<HB", message, len(fields))
    for number, size, base in fields:
        payload += bytes([number, size, base])
    return bytes(payload)


def _broken_units_fit() -> bytes:
    """A workout whose step times were written in minutes, so they read as 0.24 s."""
    data = _definition(0, 0, [(0, 1, 0x00)]) + b"\x00" + struct.pack("<B", 5)
    name = b"Broken\x00"
    data += _definition(1, 26, [(4, 1, 0x00), (8, len(name), 0x07)])
    data += b"\x01" + struct.pack("<B", 2) + name
    data += _definition(2, 27, [(254, 2, 0x84), (1, 1, 0x00), (2, 4, 0x86), (3, 1, 0x00), (7, 1, 0x00)])
    data += b"\x02" + struct.pack("<H", 0) + struct.pack("<BIBB", 0, 240, 2, 2)
    data += b"\x02" + struct.pack("<H", 1) + struct.pack("<BIBB", 0, 180, 2, 2)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


def _activity_fit() -> bytes:
    """A FIT file whose file_id type is activity, the file the user picked by mistake."""
    data = _definition(0, 0, [(0, 1, 0x00)]) + b"\x00" + struct.pack("<B", 4)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


def _base64(payload: bytes) -> str:
    return base64.b64encode(payload).decode()
