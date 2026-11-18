import os
import struct
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from garminconnect import GarminConnectConnectionError
from fitdecode.utils import compute_crc

from app.garmin.device import (
    WorkoutDeviceError,
    WorkoutNotPushed,
    WorkoutRateLimited,
    list_devices,
    parse_device_id,
    push_workout,
    resolve_device,
)
from app.main import app

_DEVICES = [
    {"deviceId": 111, "displayName": "Edge 530", "deviceCategories": ["bike_computer"]},
    {"deviceId": 222, "displayName": "Forerunner 955", "deviceCategories": ["watch_fitness"]},
]
_PRIMARY = {"PrimaryTrainingDevice": {"deviceId": 222}}
_LAST_USED = {"userDeviceId": 111}


def _client(
    devices: list[dict] | None = None,
    primary: dict | None = None,
    last_used: dict | None = None,
) -> MagicMock:
    client = MagicMock()
    client.get_devices.return_value = _DEVICES if devices is None else devices
    client.get_primary_training_device.return_value = _PRIMARY if primary is None else primary
    client.get_device_last_used.return_value = _LAST_USED if last_used is None else last_used
    client.get_activities.return_value = []
    return client


class ListDevicesTest(unittest.TestCase):
    def test_marks_the_primary_training_device(self) -> None:
        report = list_devices(_client())
        self.assertEqual(report["primary_device_id"], 222)
        self.assertEqual(
            [(device["device_id"], device["primary"]) for device in report["devices"]],
            [(111, False), (222, True)],
        )
        self.assertEqual(report["devices"][0]["name"], "Edge 530")

    def test_a_missing_primary_device_is_reported_as_none(self) -> None:
        client = _client(primary={})
        report = list_devices(client)
        self.assertIsNone(report["primary_device_id"])
        self.assertFalse(any(device["primary"] for device in report["devices"]))

    def test_a_device_list_that_is_not_a_list_fails(self) -> None:
        with self.assertRaises(WorkoutDeviceError):
            list_devices(_client(devices={"devices": []}))

    def test_client_errors_are_not_swallowed(self) -> None:
        client = _client()
        client.get_devices.side_effect = GarminConnectConnectionError("down")
        with self.assertRaises(GarminConnectConnectionError):
            list_devices(client)


class ResolveDeviceTest(unittest.TestCase):
    def test_a_cycling_workout_goes_to_the_device_that_last_rode(self) -> None:
        client = _client()
        client.get_activities.return_value = [{"activityId": 1, "deviceId": 111}]
        chosen = resolve_device(client, "cycling")
        self.assertEqual(chosen, {"device_id": 111, "source": "sport"})
        client.get_activities.assert_called_once_with(0, 20, activitytype="cycling")

    def test_a_running_workout_goes_to_the_watch_that_last_ran(self) -> None:
        client = _client()
        client.get_activities.return_value = [{"activityId": 1, "deviceId": 222}]
        chosen = resolve_device(client, "running")
        self.assertEqual(chosen, {"device_id": 222, "source": "sport"})

    def test_a_strength_workout_uses_the_primary_training_device(self) -> None:
        client = _client()
        chosen = resolve_device(client, "strength_training")
        self.assertEqual(chosen, {"device_id": 222, "source": "primary"})
        client.get_activities.assert_not_called()

    def test_no_activity_for_the_sport_falls_back_to_the_primary_device(self) -> None:
        client = _client()
        chosen = resolve_device(client, "cycling")
        self.assertEqual(chosen, {"device_id": 222, "source": "primary"})

    def test_a_missing_primary_device_falls_back_to_the_last_used_device(self) -> None:
        client = _client(primary={})
        chosen = resolve_device(client, "yoga")
        self.assertEqual(chosen, {"device_id": 111, "source": "last_used"})

    def test_a_requested_device_wins(self) -> None:
        client = _client()
        chosen = resolve_device(client, "cycling", 987)
        self.assertEqual(chosen, {"device_id": 987, "source": "requested"})
        client.get_activities.assert_not_called()

    def test_no_device_at_all_fails(self) -> None:
        client = _client(primary={}, last_used={})
        with self.assertRaises(WorkoutDeviceError):
            resolve_device(client, "yoga")

    def test_activity_rows_without_a_device_are_skipped(self) -> None:
        client = _client()
        client.get_activities.return_value = [{"activityId": 1}, {"activityId": 2, "deviceId": "111"}]
        chosen = resolve_device(client, "cycling")
        self.assertEqual(chosen["device_id"], 111)

    def test_a_failing_sport_lookup_is_not_hidden(self) -> None:
        client = _client()
        client.get_activities.side_effect = GarminConnectConnectionError("down")
        with self.assertRaises(GarminConnectConnectionError):
            resolve_device(client, "running")


class PushWorkoutTest(unittest.TestCase):
    def test_a_push_reports_the_device(self) -> None:
        client = _client()
        result = push_workout(client, 55, 111)
        client.push_workout_to_device.assert_called_once_with(55, 111)
        self.assertEqual(result, {"device_id": 111, "pushed": True})

    def test_a_rate_limited_push_is_its_own_failure(self) -> None:
        client = _client()
        client.push_workout_to_device.side_effect = GarminConnectConnectionError("API Error 429 - slow down")
        with self.assertRaises(WorkoutRateLimited):
            push_workout(client, 55, 111)

    def test_any_other_push_failure_keeps_the_workout_id(self) -> None:
        client = _client()
        client.push_workout_to_device.side_effect = GarminConnectConnectionError("API Error 500")
        with self.assertRaises(WorkoutNotPushed) as caught:
            push_workout(client, 55, 111)
        self.assertEqual(caught.exception.workout_id, 55)
        self.assertEqual(caught.exception.device_id, 111)


class ParseDeviceIdTest(unittest.TestCase):
    def test_accepts_a_positive_number_or_digit_string(self) -> None:
        self.assertEqual(parse_device_id(111), 111)
        self.assertEqual(parse_device_id("111"), 111)

    def test_rejects_everything_else(self) -> None:
        for value in (None, True, 0, -1, "", "abc", 1.5, [], {}):
            with self.subTest(value=value):
                self.assertIsNone(parse_device_id(value))


class SendWorkoutRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/workouts", json={"workout": {}})
        self.assertEqual(response.status_code, 401)

    def test_rejects_a_missing_workout(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/workouts", json={}, headers={"Authorization": "Bearer expected"}
            )
        self.assertEqual(response.status_code, 400)

    def test_returns_the_upload_summary(self) -> None:
        client = TestClient(app)
        summary = {"workout_id": 55, "name": "Sweet spot", "device_id": 111}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.upload_workout", return_value=summary) as upload:
                response = client.post(
                    "/workouts",
                    json={
                        "workout": {"name": "Sweet spot", "sport": "cycling", "blocks": []},
                        "date": "2026-11-18",
                        "device_id": 111,
                        "push": True,
                    },
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)
        sent = upload.call_args.args[0]
        self.assertEqual(sent["date"], "2026-11-18")
        self.assertEqual(sent["device_id"], 111)
        self.assertTrue(sent["push"])

    def test_a_spec_problem_is_a_bad_request(self) -> None:
        client = TestClient(app)
        from app.garmin.workout import WorkoutSpecError

        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.upload_workout", side_effect=WorkoutSpecError("Sport must be cycling")):
                response = client.post(
                    "/workouts",
                    json={"workout": {"name": "x"}},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Sport must be cycling")

    def test_a_failed_push_reports_the_uploaded_workout(self) -> None:
        client = TestClient(app)
        failure = WorkoutNotPushed(55, 111)
        failure.__cause__ = WorkoutRateLimited("API Error 429")
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.upload_workout", side_effect=failure):
                response = client.post(
                    "/workouts",
                    json={"workout": {"name": "x"}, "push": True},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 429)
        self.assertIn("55", response.json()["detail"])


class SendFitRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/workouts/fit", json={"content_base64": "AA=="})
        self.assertEqual(response.status_code, 401)

    def test_rejects_content_that_is_not_base64(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/workouts/fit",
                json={"content_base64": "***"},
                headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 400)

    def test_rejects_a_file_that_is_not_a_workout(self) -> None:
        client = TestClient(app)
        payload = _activity_fit()
        import base64

        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/workouts/fit",
                json={"content_base64": base64.b64encode(payload).decode()},
                headers={"Authorization": "Bearer expected"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["reason"], "activity_file")

    def test_an_unreadable_file_reports_its_own_reason(self) -> None:
        client = TestClient(app)
        import base64

        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/workouts/fit",
                json={"content_base64": base64.b64encode(b"junk").decode()},
                headers={"Authorization": "Bearer expected"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["reason"], "unreadable")

    def test_returns_the_import_summary(self) -> None:
        client = TestClient(app)
        summary = {"workout_id": 55, "name": "Circuit", "stored": True}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.import_workout_fit", return_value=summary) as import_fit:
                response = client.post(
                    "/workouts/fit",
                    json={"content_base64": "AA==", "date": "2026-11-18"},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)
        self.assertEqual(import_fit.call_args.args[0]["date"], "2026-11-18")


class DevicesRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/workouts/devices")
        self.assertEqual(response.status_code, 401)

    def test_returns_the_device_list(self) -> None:
        client = TestClient(app)
        summary = {"devices": [], "primary_device_id": 222}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.list_workout_devices", return_value=summary):
                response = client.post(
                    "/workouts/devices", headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)


class ProbeWorkoutDeviceRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/probe/workout-device", json={})
        self.assertEqual(response.status_code, 401)

    def test_a_read_only_probe_passes_no_workout_id(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.probe_workout_device", return_value={"devices": {}}) as probe:
                response = client.post(
                    "/probe/workout-device",
                    json={},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(probe.call_args.args, (None, None))

    def test_workout_ids_are_passed_through(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.probe_workout_device", return_value={}) as probe:
                response = client.post(
                    "/probe/workout-device",
                    json={"push_workout_id": "55", "download_workout_id": 56},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(probe.call_args.args, (55, 56))

    def test_a_bad_workout_id_is_a_bad_request(self) -> None:
        client = TestClient(app)
        for value in (0, -1, "abc", True):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
                    with patch("app.main.probe_workout_device") as probe:
                        response = client.post(
                            "/probe/workout-device",
                            json={"push_workout_id": value},
                            headers={"Authorization": "Bearer expected"},
                        )
                self.assertEqual(response.status_code, 400)
                probe.assert_not_called()


def _activity_fit() -> bytes:
    data = _definition(0, 0, [(0, 1, 0x00)]) + b"\x00" + struct.pack("<B", 4)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


def _definition(local: int, message: int, fields: list[tuple[int, int, int]]) -> bytes:
    payload = bytearray([0x40 | local, 0, 0])
    payload += struct.pack("<HB", message, len(fields))
    for number, size, base in fields:
        payload += bytes([number, size, base])
    return bytes(payload)
