import hashlib
import io
import os
import struct
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import fitdecode
from fastapi.testclient import TestClient
from fitdecode.utils import compute_crc

from app.main import app
from app.normalize.day import day_metrics
from app.normalize.load import normalize_activity
from app.normalize.fit import NormalizeError, parse_activity_zip, parse_fit
from app.normalize.store import _upsert_activity, apply_stored_power_zones
from app.storage.blob import get_private
from app.storage.db import _split_sql, ensure_schema

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
        self.assertEqual(running["avg_cadence_spm"], 170)
        self.assertEqual(running["avg_step_length_mm"], 800)
        self.assertEqual(running["avg_stride_length_cm"], 160)
        self.assertEqual(running["elevation_gain_m"], 40)
        self.assertEqual(running["total_descent_m"], 15)
        self.assertEqual(running["avg_ground_contact_time_ms"], 250)
        self.assertEqual(running["avg_vertical_oscillation_cm"], 8)
        self.assertIsNone(running["avg_power_w"])
        self.assertIsNone(parsed["cycling"])
        self.assertEqual(parsed["sets"], [])
        stored = _field_names(parsed, "session")
        self.assertEqual(stored, _decoded_names(_running_fit(start), "session"))
        spo2 = _field_row(parsed, "session", "avg_spo2")
        self.assertEqual(spo2["value_num"], 97)
        self.assertEqual(spo2["unit"], "percent")
        cadence = _field_row(parsed, "session", "avg_running_cadence")
        self.assertEqual(cadence["value_num"], 85)
        self.assertEqual(cadence["unit"], "strides/min")
        metrics = {sample["metric"]: sample for sample in parsed["samples"]}
        self.assertEqual(metrics["heart_rate"]["value"], 150)
        self.assertEqual(metrics["heart_rate"]["unit"], "bpm")
        self.assertAlmostEqual(metrics["position_lat"]["value"], 47.2, places=5)
        self.assertEqual(metrics["position_lat"]["unit"], "deg")
        self.assertEqual(metrics["speed"]["unit"], "m/s")
        self.assertEqual(
            {sample["metric"] for sample in parsed["samples"]},
            _decoded_record_metrics(_running_fit(start)),
        )


class CyclingAndStrengthTest(unittest.TestCase):
    def test_indoor_cycling_keeps_the_session_and_writes_cycling_totals(self) -> None:
        payload = _cycling_fit()
        parsed = parse_fit(payload)
        self.assertEqual(parsed["sport"], "cycling")
        self.assertEqual(parsed["sub_sport"], "indoor_cycling")
        self.assertIsNone(parsed["running"])
        cycling = parsed["cycling"]
        self.assertEqual(cycling["avg_power_w"], 200)
        self.assertEqual(cycling["max_power_w"], 400)
        self.assertEqual(cycling["normalized_power_w"], 220)
        self.assertEqual(cycling["tss"], 80.5)
        self.assertEqual(cycling["intensity_factor"], 0.85)
        self.assertEqual(cycling["avg_cadence_rpm"], 90.5)
        self.assertEqual(cycling["max_cadence_rpm"], 110)
        self.assertEqual(_field_names(parsed, "session"), _decoded_names(payload, "session"))

    def test_strength_set_keeps_reps_weight_and_the_exercise_name(self) -> None:
        start = datetime(2026, 10, 7, 9, 48, 50, tzinfo=timezone.utc)
        payload = _strength_fit(start)
        parsed = parse_fit(payload)
        self.assertEqual(parsed["sport"], "training")
        self.assertEqual(parsed["sub_sport"], "strength_training")
        self.assertIsNone(parsed["running"])
        self.assertIsNone(parsed["cycling"])
        self.assertEqual(len(parsed["sets"]), 1)
        row = parsed["sets"][0]
        self.assertEqual(row["set_type"], "active")
        self.assertEqual(row["category"], "bench_press")
        self.assertEqual(row["exercise"], "barbell_bench_press")
        self.assertEqual(row["repetitions"], 8)
        self.assertEqual(row["weight_kg"], 20)
        self.assertEqual(row["duration_sec"], 30)
        self.assertEqual(row["start_at"], start)
        self.assertEqual(_field_names(parsed, "set"), _decoded_names(payload, "set"))
        self.assertEqual(_field_names(parsed, "session"), _decoded_names(payload, "session"))

    def test_undocumented_session_fields_are_named_and_scaled(self) -> None:
        parsed = parse_fit(_session_extra_fit())
        self.assertEqual(parsed["total_sets"], 12)
        self.assertEqual(parsed["volume_kg"], 250)
        self.assertEqual(parsed["est_sweat_loss_ml"], 640)
        self.assertEqual(parsed["primary_benefit"], "base")
        self.assertEqual(parsed["recovery_heart_rate"], 120)
        sets = _field_row(parsed, "session", "total_sets")
        volume = _field_row(parsed, "session", "volume")
        sweat = _field_row(parsed, "session", "est_sweat_loss")
        benefit = _field_row(parsed, "session", "primary_benefit")
        recovery = _field_row(parsed, "session", "recovery_heart_rate")
        self.assertEqual(sets["value_num"], 12)
        self.assertEqual(volume["value_num"], 250)
        self.assertEqual(volume["unit"], "kg")
        self.assertEqual(sweat["value_num"], 640)
        self.assertEqual(sweat["unit"], "ml")
        self.assertEqual(benefit["value_num"], 2)
        self.assertEqual(benefit["value_text"], "base")
        self.assertEqual(recovery["value_num"], 120)
        self.assertEqual(recovery["unit"], "bpm")
        self.assertNotIn("unknown_151", _field_names(parsed, "session"))


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

    def test_normalize_for_one_activity_uses_that_id(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.normalize_activity", return_value={"fit_file": "a.fit", "day": None}) as called:
                response = client.post(
                    "/normalize",
                    headers={"Authorization": "Bearer expected"},
                    json={"garmin_activity_id": "8"},
                )
        self.assertEqual(response.status_code, 200)
        called.assert_called_once_with(8)


class NormalizeActivityTest(unittest.TestCase):
    def test_requested_zip_is_parsed_without_a_day_file(self) -> None:
        body = b"zip-bytes"
        raw = {
            "kind": "activity",
            "garmin_activity_id": 8,
            "day": None,
            "source_format": "zip",
            "source_path": "garmin/1/activity/8/abc.zip",
            "source_sha256": hashlib.sha256(body).hexdigest(),
            "byte_size": len(body),
        }
        parsed = {
            "sport": "cycling",
            "sub_sport": "indoor_cycling",
            "start_at": None,
            "timezone_offset_min": None,
            "samples": [],
            "fields": [],
            "running": None,
            "cycling": {},
            "sets": [],
        }
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False
        order: list[str] = []
        connection.execute.side_effect = lambda statement, *_args, **_kwargs: order.append(statement)
        with patch("app.normalize.load.connect", return_value=connection):
            with patch("app.normalize.load.ensure_schema"):
                with patch("app.normalize.load.latest_activity_raw_object", return_value=raw):
                    with patch(
                        "app.normalize.load.load_activity_meta",
                        return_value={"start_local": "2026-10-07 18:47:45"},
                    ):
                        with patch("app.normalize.load.get_private", return_value=body) as download:
                            with patch(
                                "app.normalize.load.parse_activity_zip",
                                return_value=("8.fit", parsed),
                            ):
                                with patch("app.normalize.load.find_day_raw_object", return_value=None):
                                    with patch(
                                        "app.normalize.load.write_normalized",
                                        return_value={"activity": {"garmin_activity_id": 8}, "day": None},
                                    ) as write:
                                        write.side_effect = lambda *_args, **_kwargs: order.append("write") or {
                                            "activity": {"garmin_activity_id": 8},
                                            "day": None,
                                        }
                                        result = normalize_activity(8)
        download.assert_called_once_with("garmin/1/activity/8/abc.zip")
        self.assertEqual(write.call_args.kwargs["garmin_activity_id"], 8)
        self.assertIsNone(write.call_args.kwargs["day"])
        self.assertEqual(result["fit_file"], "8.fit")
        self.assertEqual(order[0].split("(")[0], "SELECT pg_advisory_lock")
        self.assertEqual(order[-1].split("(")[0], "SELECT pg_advisory_unlock")
        self.assertLess(order.index("write"), order.index(order[-1]))


class SchemaLockTest(unittest.TestCase):
    def test_schema_update_waits_for_the_parse_lock(self) -> None:
        connection = MagicMock()
        ensure_schema(connection)
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertEqual(statements[0].split("(")[0], "SELECT pg_advisory_lock")
        self.assertEqual(statements[-1].split("(")[0], "SELECT pg_advisory_unlock")
        connection.commit.assert_called_once()


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
        (23, 2, 0x84),
        (134, 2, 0x84),
        (194, 1, 0x02),
    ]
    session_values = struct.pack(
        "<IBBIIIH" + "H" + "BBBH" + "B" + "5I" + "HHB" + "HHB",
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
        15,
        8000,
        97,
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


def _cycling_fit() -> bytes:
    start = datetime(2026, 10, 7, 15, 47, 45, tzinfo=timezone.utc)
    raw = int((start - _FIT_EPOCH).total_seconds())
    fields = [
        (2, 4, 0x86),
        (5, 1, 0x00),
        (6, 1, 0x00),
        (18, 1, 0x02),
        (19, 1, 0x02),
        (20, 2, 0x84),
        (21, 2, 0x84),
        (34, 2, 0x84),
        (35, 2, 0x84),
        (36, 2, 0x84),
        (92, 1, 0x02),
    ]
    values = struct.pack("<IBBBBHHHHHB", raw, 2, 6, 90, 110, 200, 400, 220, 805, 850, 64)
    return _fit_file(_definition(0, 18, fields) + _message(0, values))


def _strength_fit(start: datetime) -> bytes:
    raw = int((start - _FIT_EPOCH).total_seconds())
    session = _definition(0, 18, [(2, 4, 0x86), (5, 1, 0x00), (6, 1, 0x00)])
    session += _message(0, struct.pack("<IBB", raw, 10, 20))
    fields = [
        (0, 4, 0x86),
        (3, 2, 0x84),
        (4, 2, 0x84),
        (5, 1, 0x00),
        (6, 4, 0x86),
        (7, 2, 0x84),
        (8, 2, 0x84),
    ]
    values = struct.pack("<IHHB" + "IHH", 30_000, 8, 320, 1, raw, 0, 1)
    return _fit_file(session + _definition(1, 225, fields) + _message(1, values))


def _session_extra_fit() -> bytes:
    fields = [
        (5, 1, 0x00),
        (151, 2, 0x84),
        (152, 4, 0x86),
        (178, 2, 0x84),
        (188, 1, 0x00),
        (202, 1, 0x02),
    ]
    values = struct.pack("<BHIHBB", 1, 12, 25000, 640, 2, 120)
    return _fit_file(_definition(0, 18, fields) + _message(0, values))


def _field_names(parsed: dict[str, Any], message: str) -> set[str]:
    return {row["name"] for row in parsed["fields"] if row["message"] == message}


def _field_row(parsed: dict[str, Any], message: str, name: str) -> dict[str, Any]:
    matches = [
        row
        for row in parsed["fields"]
        if row["message"] == message and row["name"] == name and row["ordinal"] == 0
    ]
    if len(matches) != 1:
        raise AssertionError(f"{message}.{name} appeared {len(matches)} times")
    return matches[0]


def _decoded_names(payload: bytes, message_name: str) -> set[str]:
    names: set[str] = set()
    with fitdecode.FitReader(io.BytesIO(payload)) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != message_name:
                continue
            for field in frame.fields:
                if _decoded_present(field):
                    names.add(field.name)
    return names


def _decoded_record_metrics(payload: bytes) -> set[str]:
    metrics: set[str] = set()
    with fitdecode.FitReader(io.BytesIO(payload)) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != "record":
                continue
            for field in frame.fields:
                if field.name == "timestamp" or not _decoded_present(field):
                    continue
                if isinstance(field.value, (list, tuple)):
                    metrics.update(
                        f"{field.name}_{index}"
                        for index, item in enumerate(field.value)
                        if _value_present(item, field.units)
                    )
                else:
                    metrics.add(field.name)
    return metrics


def _decoded_present(field: Any) -> bool:
    return _value_present(field.value, field.units)


def _value_present(value: Any, units: str | None) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return any(_value_present(item, units) for item in value)
    if isinstance(value, str):
        return bool(value)
    if units == "semicircles" and isinstance(value, int) and value == 0x7FFFFFFF:
        return False
    return True


def _fit_file(data: bytes) -> bytes:
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(data), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    return header + data + struct.pack("<H", compute_crc(data))


class StoredHeartRateZoneTest(unittest.TestCase):
    def test_fit_without_zones_keeps_stored_zeros(self) -> None:
        connection = MagicMock()
        stored = MagicMock()
        stored.fetchone.return_value = (1983, 1029, 2, 0, 0)
        inserted = MagicMock()
        inserted.fetchone.return_value = (4,)
        connection.execute.side_effect = [stored, inserted]
        parsed = {
            "sport": "cycling",
            "sub_sport": "road",
            "start_at": None,
            "end_at": None,
            "duration_sec": 3360,
            "moving_duration_sec": 3360,
            "elapsed_duration_sec": 3411,
            "timezone_offset_min": 180,
            "distance_m": 1000,
            "avg_hr": 109,
            "max_hr": 135,
            "avg_speed": 11,
            "calories": 486,
            "aerobic_effect": 2.7,
            "anaerobic_effect": 0.1,
            "garmin_activity_load": 60,
            "hr_zone_3_sec": 9,
        }
        _upsert_activity(
            connection,
            9,
            parsed,
            {"source_format": "zip", "source_path": "garmin/1/a.zip", "source_sha256": "abc"},
        )
        params = connection.execute.call_args_list[1].args[1]
        names = (
            "garmin_activity_id",
            "sport",
            "sub_sport",
            "garmin_type_key",
            "start_at",
            "end_at",
            "duration_sec",
            "moving_duration_sec",
            "elapsed_duration_sec",
            "timezone_offset_min",
            "distance_m",
            "avg_hr",
            "max_hr",
            "avg_speed",
            "calories",
            "aerobic_effect",
            "anaerobic_effect",
            "training_effect_label",
            "garmin_activity_load",
            "hr_zone_1_sec",
            "hr_zone_2_sec",
            "hr_zone_3_sec",
            "hr_zone_4_sec",
            "hr_zone_5_sec",
        )
        row = dict(zip(names, params))
        self.assertEqual(row["hr_zone_1_sec"], 1983.0)
        self.assertEqual(row["hr_zone_3_sec"], 9)
        self.assertEqual(row["hr_zone_4_sec"], 0.0)
        self.assertEqual(row["hr_zone_5_sec"], 0.0)


class StoredPowerZoneTest(unittest.TestCase):
    def test_missing_fit_power_zones_keep_stored_zeros(self) -> None:
        cycling = {"avg_power_w": 123.0, "power_zone_2_sec": 4}
        apply_stored_power_zones(
            cycling,
            {"power_zone_1_sec": 2067.0, "power_zone_2_sec": 170.0, "power_zone_7_sec": 0.0},
        )
        self.assertEqual(cycling["power_zone_1_sec"], 2067.0)
        self.assertEqual(cycling["power_zone_2_sec"], 4)
        self.assertEqual(cycling["power_zone_7_sec"], 0.0)


if __name__ == "__main__":
    unittest.main()
