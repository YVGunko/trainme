import io
import os
import struct
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from fitdecode.utils import compute_crc

from app.main import app
from app.normalize.day import day_metrics
from app.normalize.fit import NormalizeError, parse_activity_zip
from app.storage.blob import get_private
from app.storage.db import _split_sql

_FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)


class DayMetricsTest(unittest.TestCase):
    def test_reads_only_sleep_and_resting_heart_rate_fields(self) -> None:
        payload = {
            "sleep": {
                "dailySleepDTO": {
                    "sleepTimeSeconds": 25000,
                    "napTimeSeconds": 600,
                    "avgSleepHRV": 42,
                    "sleepScores": {"overall": {"value": 80, "qualifierKey": "GOOD"}},
                }
            },
            "heart_rate": {"restingHeartRate": 48, "heartRateValues": [[1, 50]]},
        }
        self.assertEqual(
            day_metrics(payload),
            {
                "sleep_duration_sec": 25000.0,
                "sleep_score": 80.0,
                "overnight_hrv": 42.0,
                "resting_hr": 48.0,
            },
        )


class FitParseTest(unittest.TestCase):
    def test_zip_without_a_fit_file_is_rejected(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", "not a fit")
        with self.assertRaises(NormalizeError) as caught:
            parse_activity_zip(buffer.getvalue())
        self.assertIn("FIT", str(caught.exception))

    def test_running_fit_maps_profile_units(self) -> None:
        start = datetime(2026, 10, 9, 4, 21, 13, tzinfo=timezone.utc)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("activity.fit", _running_fit(start))
        name, parsed = parse_activity_zip(buffer.getvalue())
        self.assertEqual(name, "activity.fit")
        self.assertEqual(parsed["sport"], "running")
        self.assertEqual(parsed["duration_sec"], 3500)
        self.assertEqual(parsed["elapsed_duration_sec"], 3600)
        self.assertEqual(parsed["distance_m"], 10000)
        self.assertEqual(parsed["avg_speed"], 3)
        self.assertEqual(parsed["avg_hr"], 140)
        self.assertEqual(parsed["calories"], 400)
        self.assertEqual(parsed["aerobic_effect"], 3.5)
        self.assertEqual(parsed["anaerobic_effect"], 1.2)
        self.assertEqual(parsed["hr_zone_1_sec"], 10)
        self.assertEqual(parsed["hr_zone_5_sec"], 50)
        self.assertEqual(parsed["timezone_offset_min"], 180)
        self.assertEqual(parsed["end_at"], start + timedelta(seconds=3600))
        running = parsed["running"]
        self.assertIsNone(running["avg_cadence_spm"])
        self.assertIsNone(running["avg_stride_length_cm"])
        self.assertEqual(running["elevation_gain_m"], 40)
        self.assertEqual(running["avg_ground_contact_time_ms"], 250)
        self.assertEqual(running["avg_vertical_oscillation_cm"], 8)
        metrics = {sample["metric"]: sample for sample in parsed["samples"]}
        self.assertEqual(metrics["heart_rate"]["value"], 150)
        self.assertEqual(metrics["heart_rate"]["unit"], "bpm")
        self.assertAlmostEqual(metrics["gps_lat"]["value"], 47.2, places=5)
        self.assertEqual(metrics["speed"]["unit"], "m/s")


class BlobReadTest(unittest.TestCase):
    def test_get_reads_a_private_blob_by_pathname(self) -> None:
        response = MagicMock()
        response.read.return_value = b"zip"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.dict(
            os.environ,
            {"BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_store123_secret"},
            clear=False,
        ):
            with patch("app.storage.blob.urllib.request.urlopen", return_value=response) as urlopen:
                body = get_private("garmin/1/activity/9/abc.zip")
        self.assertEqual(body, b"zip")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(
            request.full_url,
            "https://store123.private.blob.vercel-storage.com/garmin/1/activity/9/abc.zip?cache=0",
        )
        self.assertTrue(request.get_header("Authorization").startswith("Bearer "))


class NormalizeRouteTest(unittest.TestCase):
    def test_normalize_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/normalize")
        self.assertEqual(response.status_code, 401)

    def test_normalize_returns_the_summary(self) -> None:
        summary = {
            "fit_file": "activity.fit",
            "activity": {"garmin_activity_id": 9, "sport": "running", "sample_count": 1},
            "day": {"date": "2026-10-09", "fields": ["sleep_duration_sec"]},
        }
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.normalize_latest", return_value=summary):
                response = client.post(
                    "/normalize",
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["fit_file"], "activity.fit")
        self.assertNotIn("di_token", response.text)


class MigrationSqlTest(unittest.TestCase):
    def test_foreign_key_block_stays_one_statement(self) -> None:
        script = (
            "CREATE TABLE IF NOT EXISTS activity (id bigint);\n"
            "DO $$\nBEGIN\n    ALTER TABLE activity ADD CONSTRAINT activity_fkey FOREIGN KEY (id) REFERENCES activity(id);\n"
            "EXCEPTION\n    WHEN duplicate_object THEN NULL;\nEND $$;\n"
        )
        statements = _split_sql(script)
        self.assertEqual(len(statements), 2)
        self.assertTrue(statements[1].startswith("DO $$"))


def _running_fit(start: datetime) -> bytes:
    raw = int((start - _FIT_EPOCH).total_seconds())
    latitude = round(47.2 * (2**31) / 180)
    longitude = round(39.7 * (2**31) / 180)
    session_fields = [
        (2, 4, 0x86),
        (5, 1, 0x00),
        (6, 1, 0x00),
        (7, 4, 0x86),
        (8, 4, 0x86),
        (9, 4, 0x86),
        (11, 2, 0x84),
        (14, 2, 0x84),
        (16, 1, 0x02),
        (17, 1, 0x02),
        (18, 1, 0x02),
        (22, 2, 0x84),
        (24, 1, 0x02),
        (65, 20, 0x86),
        (89, 2, 0x84),
        (91, 2, 0x84),
        (137, 1, 0x02),
    ]
    session_values = struct.pack(
        "<IBBIIIH" + "H" + "BBBH" + "B" + "5I" + "HHB",
        raw,
        1,
        0,
        3_600_000,
        3_500_000,
        1_000_000,
        400,
        3000,
        140,
        170,
        85,
        40,
        35,
        10_000,
        20_000,
        30_000,
        40_000,
        50_000,
        800,
        2500,
        12,
    )
    data = _definition(0, 18, session_fields) + _message(0, session_values)
    data += _definition(1, 34, [(253, 4, 0x86), (5, 4, 0x86)])
    data += _message(1, struct.pack("<II", raw, raw + 180 * 60))
    data += _definition(
        2,
        20,
        [(253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85), (3, 1, 0x02), (4, 1, 0x02), (6, 2, 0x84)],
    )
    data += _message(2, struct.pack("<IiiBBH", raw, latitude, longitude, 150, 86, 2800))
    return _fit_file(data)


def _definition(local: int, message: int, fields: list[tuple[int, int, int]]) -> bytes:
    payload = bytearray([0x40 | local, 0, 0])
    payload += struct.pack("<HB", message, len(fields))
    for number, size, base in fields:
        payload += bytes([number, size, base])
    return bytes(payload)


def _message(local: int, payload: bytes) -> bytes:
    return bytes([local]) + payload


def _fit_file(data: bytes) -> bytes:
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


if __name__ == "__main__":
    unittest.main()
