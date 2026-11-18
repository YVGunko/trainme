import unittest
from unittest.mock import MagicMock, patch

from garminconnect import GarminConnectConnectionError

from app.garmin.workout_probe import probe_complete, probe_workout_device

_DEVICES = [{"deviceId": 111, "displayName": "Edge 530"}]
_PRIMARY = {"PrimaryTrainingDevice": {"deviceId": 222}}


def _client() -> MagicMock:
    client = MagicMock()
    client.get_devices.return_value = _DEVICES
    client.get_primary_training_device.return_value = _PRIMARY
    client.get_device_last_used.return_value = {"userDeviceId": 111}
    client.get_activities.return_value = [{"activityId": 1, "deviceId": 111}]
    client.get_workout_by_id.return_value = {
        "workoutId": 55,
        "workoutName": "Sweet spot",
        "sportType": {"sportTypeKey": "cycling"},
    }
    client.push_workout_to_device.return_value = {"ok": True}
    return client


class ProbeWorkoutDeviceTest(unittest.TestCase):
    def test_a_read_only_run_does_not_push(self) -> None:
        client = _client()
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device()
        client.push_workout_to_device.assert_not_called()
        self.assertTrue(probe_complete(report))
        self.assertNotIn("push", report)
        self.assertEqual(report["sport_device"]["cycling"]["payload"]["device_id"], 111)

    def test_a_named_workout_is_pushed_to_its_sport_device(self) -> None:
        client = _client()
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device(55)
        client.push_workout_to_device.assert_called_once_with(55, 111)
        self.assertTrue(report["push"]["sent"]["ok"])
        self.assertTrue(probe_complete(report))

    def test_a_failed_push_marks_the_report_incomplete(self) -> None:
        client = _client()
        client.push_workout_to_device.side_effect = GarminConnectConnectionError("API Error 429")
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device(55)
        self.assertFalse(report["push"]["sent"]["ok"])
        self.assertFalse(probe_complete(report))

    def test_a_missing_device_list_marks_the_report_incomplete(self) -> None:
        client = _client()
        client.get_devices.side_effect = GarminConnectConnectionError("down")
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device()
        self.assertFalse(report["devices"]["ok"])
        self.assertFalse(probe_complete(report))

    def test_secret_shaped_keys_are_redacted(self) -> None:
        client = _client()
        client.get_device_last_used.return_value = {
            "userDeviceId": 111,
            "access_token": "abc",
            "refreshToken": "def",
        }
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device()
        payload = report["last_used"]["payload"]
        self.assertEqual(payload["access_token"], "<redacted>")
        self.assertEqual(payload["refreshToken"], "<redacted>")
        self.assertEqual(payload["userDeviceId"], 111)

    def test_a_workout_without_a_sport_uses_the_primary_device(self) -> None:
        client = _client()
        client.get_workout_by_id.return_value = {"workoutId": 55}
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device(55)
        self.assertEqual(report["push"]["device"]["payload"], {"device_id": 222, "source": "primary"})

    def test_a_downloaded_workout_is_read_by_the_importer(self) -> None:
        client = _client()
        client.download_workout.return_value = _running_fit()
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device(download_workout_id=55)
        self.assertTrue(report["download"]["parsed"])
        self.assertEqual(report["download"]["spec"]["sport"], "running")
        self.assertTrue(probe_complete(report))
        client.push_workout_to_device.assert_not_called()

    def test_a_downloaded_file_the_importer_cannot_read_is_reported(self) -> None:
        client = _client()
        client.download_workout.return_value = b"not a fit file"
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device(download_workout_id=55)
        self.assertFalse(report["download"]["parsed"])
        self.assertFalse(probe_complete(report))

    def test_a_download_that_is_not_bytes_is_reported(self) -> None:
        client = _client()
        client.download_workout.return_value = None
        with patch("app.garmin.workout_probe._open_client", return_value=client):
            report = probe_workout_device(download_workout_id=55)
        self.assertFalse(report["download"]["ok"])


def _running_fit() -> bytes:
    import struct

    from fitdecode.utils import compute_crc

    name = b"Easy\x00"
    data = _definition(0, [(0, 1, 0x00)]) + b"\x00" + struct.pack("<B", 5)
    data += _definition(1, [(4, 1, 0x00), (8, len(name), 0x07)]) + b"\x01" + struct.pack("<B", 1) + name
    data += _definition(2, [(254, 2, 0x84), (1, 1, 0x00), (2, 4, 0x86), (3, 1, 0x00), (7, 1, 0x00)])
    data += b"\x02" + struct.pack("<H", 0) + struct.pack("<BIBB", 0, 300000, 2, 2)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


def _definition(local: int, fields: list[tuple[int, int, int]]) -> bytes:
    import struct

    message = 0 if local == 0 else 26 if local == 1 else 27
    payload = bytearray([0x40 | local, 0, 0])
    payload += struct.pack("<HB", message, len(fields))
    for number, size, base in fields:
        payload += bytes([number, size, base])
    return bytes(payload)
