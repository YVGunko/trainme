import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.garmin.workout import (
    WorkoutDateError,
    WorkoutNotScheduled,
    WorkoutSpecError,
    build_test_strength_workout,
    build_workout,
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
        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key"}):
            with patch("app.garmin.workout.connect") as connect:
                connect.return_value.__enter__.return_value = MagicMock()
                with patch("app.garmin.workout.load_token", return_value="saved"):
                    with patch("app.garmin.workout._login", return_value=client):
                        with patch("app.garmin.workout.save_token"):
                            result = upload_workout(spec)
        sent = client.upload_workout.call_args.args[0]
        self.assertEqual(sent["sportType"]["sportTypeKey"], "yoga")
        self.assertEqual(sent["workoutSegments"][0]["workoutSteps"][0]["exerciseName"], "STRETCH_PIGEON_POSE")
        client.schedule_workout.assert_not_called()
        self.assertEqual(result, {"workout_id": 9, "name": "Hips"})


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

        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key"}):
            with patch("app.garmin.workout.connect") as connect:
                connect.return_value.__enter__.return_value = MagicMock()
                with patch("app.garmin.workout.load_token", return_value="saved"):
                    with patch("app.garmin.workout._login", return_value=client):
                        with patch("app.garmin.workout.save_token") as save_token:
                            result = schedule_test_strength_workout("2026-10-13")

        uploaded = client.upload_workout.call_args.args[0]
        self.assertEqual(uploaded["workoutSegments"][0]["workoutSteps"][1]["workoutSteps"][0]["weightValue"], 5.0)
        client.schedule_workout.assert_called_once_with(55, "2026-10-13")
        save_token.assert_called_once()
        self.assertEqual(result, {"workout_id": 55, "date": "2026-10-13", "name": "trainme test"})

    def test_keeps_the_id_when_scheduling_fails(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.upload_workout.return_value = {"workoutId": 55}
        client.schedule_workout.side_effect = RuntimeError("calendar down")

        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key"}):
            with patch("app.garmin.workout.connect") as connect:
                connect.return_value.__enter__.return_value = MagicMock()
                with patch("app.garmin.workout.load_token", return_value=None):
                    with patch("app.garmin.workout._login", return_value=client):
                        with patch("app.garmin.workout.save_token"):
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
