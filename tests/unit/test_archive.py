import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.storage.db import save_hr_zone_seconds, save_power_zone_seconds, upsert_activity_meta
from app.garmin.archive import (
    PeriodError,
    _activity_day,
    _store_bytes,
    archive_latest,
    archive_period,
    list_hr_zone_seconds,
    refresh_stored_days,
    list_power_zone_seconds,
    parse_period,
)
from app.main import app
from app.storage.blob import put_private
from app.storage.crypto import decrypt, encrypt


class CryptoTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        payload = encrypt('{"di_token":"secret"}', "local-key")
        self.assertNotIn(b"secret", payload)
        self.assertEqual(decrypt(payload, "local-key"), '{"di_token":"secret"}')


class ArchiveRouteTest(unittest.TestCase):
    def test_archive_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/archive")
        self.assertEqual(response.status_code, 401)

    def test_archive_returns_the_storage_summary(self) -> None:
        summary = {
            "activity": {
                "kind": "activity",
                "source_format": "zip",
                "source_path": "garmin/1/activity/9/abc.zip",
                "source_sha256": "abc",
                "byte_size": 4,
                "stored": True,
            },
            "day": {
                "kind": "day",
                "day": "2026-10-09",
                "source_format": "json",
                "source_path": "garmin/1/day/2026-10-09/def.json",
                "source_sha256": "def",
                "byte_size": 8,
                "stored": True,
            },
        }
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.archive_latest", return_value=summary):
                response = client.post(
                    "/archive",
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)
        self.assertNotIn("di_token", response.text)


class StoreBytesTest(unittest.TestCase):
    def test_existing_hash_is_not_uploaded_again(self) -> None:
        connection = MagicMock()
        existing = {
            "kind": "activity",
            "source_path": "garmin/1/activity/9/abc.zip",
            "source_sha256": "abc",
        }
        with patch("app.garmin.archive.find_raw_object", return_value=existing):
            with patch("app.garmin.archive.put_private") as upload:
                record = _store_bytes(
                    connection,
                    body=b"zip",
                    kind="activity",
                    source_format="zip",
                    pathname="garmin/1/activity/9",
                    extension="zip",
                    content_type="application/zip",
                    garmin_activity_id=9,
                    day=None,
                )
        upload.assert_not_called()
        self.assertFalse(record["stored"])

    def test_activity_day_uses_the_local_date(self) -> None:
        self.assertEqual(_activity_day({"startTimeLocal": "2026-10-09 07:21:13"}), "2026-10-09")


class ArchiveSelectionTest(unittest.TestCase):
    def test_stored_latest_activity_is_not_downloaded_again(self) -> None:
        client = _garmin_client(
            [
                {"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"},
                {"activityId": 8, "startTimeLocal": "2026-10-07 18:47:45"},
            ]
        )
        with _archive_patches(client, activity_ids={9}, days={"2026-10-09"}):
            result = archive_latest()
        client.download_activity.assert_called_once()
        self.assertEqual(client.download_activity.call_args.args[0], "8")
        client.get_sleep_data.assert_called_once_with("2026-10-07")
        self.assertEqual(result["activity"]["garmin_activity_id"], 8)
        self.assertTrue(result["activity"]["stored"])

    def test_stored_activity_with_a_missing_day_does_not_redownload_the_zip(self) -> None:
        client = _garmin_client(
            [{"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"}]
        )
        with _archive_patches(client, activity_ids={9}, days=set()):
            result = archive_latest()
        client.download_activity.assert_not_called()
        client.get_sleep_data.assert_called_once_with("2026-10-09")
        self.assertFalse(result["activity"]["stored"])
        self.assertTrue(result["day"]["stored"])

    def test_fully_stored_page_does_not_call_garmin_files(self) -> None:
        client = _garmin_client(
            [
                {"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"},
                {"activityId": 8, "startTimeLocal": "2026-10-07 18:47:45"},
            ]
        )
        with _archive_patches(client, activity_ids={9, 8}, days={"2026-10-09", "2026-10-07"}):
            result = archive_latest()
        client.download_activity.assert_not_called()
        client.get_sleep_data.assert_not_called()
        client.get_heart_rates.assert_not_called()
        self.assertFalse(result["activity"]["stored"])
        self.assertEqual(result["activity"]["garmin_activity_id"], 9)
        self.assertEqual(result["day"]["day"], "2026-10-09")

    def test_new_activity_on_a_stored_day_does_not_refetch_the_day(self) -> None:
        client = _garmin_client(
            [{"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"}]
        )
        with _archive_patches(client, activity_ids=set(), days={"2026-10-09"}):
            result = archive_latest()
        client.download_activity.assert_called_once()
        client.get_sleep_data.assert_not_called()
        client.get_heart_rates.assert_not_called()
        self.assertTrue(result["activity"]["stored"])
        self.assertFalse(result["day"]["stored"])


class ActivityMetaTest(unittest.TestCase):
    def test_garmin_update_does_not_replace_user_text(self) -> None:
        connection = MagicMock()
        upsert_activity_meta(connection, 9, "Morning", "2026-10-09 07:21:13")
        sql = connection.execute.call_args.args[0]
        self.assertIn("garmin_name = COALESCE", sql)
        self.assertNotIn("title =", sql)
        self.assertNotIn("description =", sql)

    def test_zone_seconds_update_the_activity_row_including_zero(self) -> None:
        connection = MagicMock()
        save_hr_zone_seconds(connection, 9, {"hr_zone_1_sec": 10.0, "hr_zone_5_sec": 0.0})
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertIn("UPDATE activity", statements[1])
        self.assertEqual(connection.execute.call_args_list[1].args[1], (10.0, 0.0, 9))
        connection.commit.assert_called_once()

    def test_power_zone_seconds_update_the_cycling_row_including_zero(self) -> None:
        connection = MagicMock()
        save_power_zone_seconds(connection, 9, {"power_zone_1_sec": 2067.0, "power_zone_7_sec": 0.0})
        statements = [call.args[0] for call in connection.execute.call_args_list]
        self.assertIn("UPDATE cycling_activity", statements[1])
        self.assertNotIn("UPDATE activity\n", statements[1])
        self.assertEqual(connection.execute.call_args_list[1].args[1], (2067.0, 0.0, 9))


class PeriodTest(unittest.TestCase):
    def test_period_rejects_more_than_14_days(self) -> None:
        with self.assertRaises(PeriodError):
            parse_period("2026-10-01", "2026-10-15")

    def test_period_keeps_stored_files_and_records_the_garmin_name(self) -> None:
        client = _garmin_client([])
        client.get_activities_by_date.return_value = [
            {
                "activityId": 9,
                "activityName": "Morning",
                "startTimeLocal": "2026-10-09 07:21:13",
            },
            {
                "activityId": 8,
                "activityName": "Bike",
                "startTimeLocal": "2026-10-07 18:47:45",
            },
        ]
        remembered: list[tuple] = []

        def remember(activity_id: int, name: str | None, start: str | None) -> None:
            remembered.append((activity_id, name, start))

        with _archive_patches(client, activity_ids={9}, days={"2026-10-09"}):
            with patch("app.garmin.archive._remember_activity", side_effect=remember):
                result = archive_period("2026-10-07", "2026-10-09")

        client.get_activities_by_date.assert_called_once_with("2026-10-07", "2026-10-09")
        client.download_activity.assert_called_once()
        self.assertEqual(client.download_activity.call_args.args[0], "8")
        self.assertEqual(client.get_sleep_data.call_count, 2)
        self.assertEqual(result["activity_count"], 2)
        self.assertEqual(result["downloaded_activity_count"], 1)
        self.assertEqual(result["day_count"], 3)
        self.assertEqual(result["downloaded_day_count"], 2)
        self.assertEqual(
            result["activities"],
            [
                {"garmin_activity_id": 9, "day": "2026-10-09", "stored": False},
                {"garmin_activity_id": 8, "day": "2026-10-07", "stored": True},
            ],
        )
        self.assertIn((9, "Morning", "2026-10-09 07:21:13"), remembered)
        self.assertIn((8, "Bike", "2026-10-07 18:47:45"), remembered)

    def test_period_writes_zone_seconds_for_an_already_stored_activity(self) -> None:
        client = _garmin_client([])
        client.get_activities_by_date.return_value = [
            {
                "activityId": 9,
                "activityName": "Bike",
                "startTimeLocal": "2026-10-14 10:13:05",
                "hrTimeInZone_1": 1983,
                "hrTimeInZone_2": 1029,
                "hrTimeInZone_3": 2,
                "hrTimeInZone_4": 0,
                "hrTimeInZone_5": 0,
            }
        ]
        with _archive_patches(client, activity_ids={9}, days={"2026-10-14"}):
            with patch("app.garmin.archive.upsert_activity_meta"):
                with patch("app.garmin.archive.save_hr_zone_seconds") as save:
                    archive_period("2026-10-14", "2026-10-14")
        client.download_activity.assert_not_called()
        save.assert_called_once()
        self.assertEqual(save.call_args.args[1], 9)
        self.assertEqual(
            save.call_args.args[2],
            {
                "hr_zone_1_sec": 1983.0,
                "hr_zone_2_sec": 1029.0,
                "hr_zone_3_sec": 2.0,
                "hr_zone_4_sec": 0.0,
                "hr_zone_5_sec": 0.0,
            },
        )

    def test_zone_seconds_keep_zero_and_skip_missing_values(self) -> None:
        self.assertEqual(
            list_hr_zone_seconds({"hrTimeInZone_1": 0, "hrTimeInZone_2": None, "hrTimeInZone_3": False}),
            {"hr_zone_1_sec": 0.0},
        )

    def test_period_writes_power_zone_seconds_for_an_already_stored_ride(self) -> None:
        client = _garmin_client([])
        client.get_activities_by_date.return_value = [
            {
                "activityId": 9,
                "activityName": "Bike",
                "startTimeLocal": "2026-10-14 10:13:05",
                "powerTimeInZone_1": 2067,
                "powerTimeInZone_2": 170,
                "powerTimeInZone_3": 187,
                "powerTimeInZone_4": 137,
                "powerTimeInZone_5": 249,
                "powerTimeInZone_6": 517,
                "powerTimeInZone_7": 33,
            }
        ]
        with _archive_patches(client, activity_ids={9}, days={"2026-10-14"}):
            with patch("app.garmin.archive.upsert_activity_meta"):
                with patch("app.garmin.archive.save_power_zone_seconds") as save:
                    archive_period("2026-10-14", "2026-10-14")
        client.download_activity.assert_not_called()
        save.assert_called_once()
        self.assertEqual(
            save.call_args.args[2],
            {
                "power_zone_1_sec": 2067.0,
                "power_zone_2_sec": 170.0,
                "power_zone_3_sec": 187.0,
                "power_zone_4_sec": 137.0,
                "power_zone_5_sec": 249.0,
                "power_zone_6_sec": 517.0,
                "power_zone_7_sec": 33.0,
            },
        )
        self.assertEqual(
            list_power_zone_seconds({"powerTimeInZone_7": 0, "powerTimeInZone_1": False}),
            {"power_zone_7_sec": 0.0},
        )

    def test_period_route_rejects_a_long_range(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/archive/period",
                headers={"Authorization": "Bearer expected"},
                json={"start": "2026-10-01", "end": "2026-10-20"},
            )
        self.assertEqual(response.status_code, 400)

    def test_period_writes_daily_metrics_without_redownloading_sleep(self) -> None:
        client = _garmin_client([])
        client.get_activities_by_date.return_value = []
        client.get_hrv_data.return_value = {
            "hrvSummary": {"status": "UNBALANCED"},
            "hrvReadings": [{"value": 1}],
        }
        client.get_training_readiness.return_value = [
            {
                "primaryActivityTracker": True,
                "timestamp": "2026-10-15T02:36:22.0",
                "score": 70,
                "level": "LOW",
            },
            {
                "primaryActivityTracker": True,
                "timestamp": "2026-10-15T03:57:13.0",
                "score": 76,
                "level": "HIGH",
            },
        ]
        client.get_daily_training_status.return_value = {
            "latestTrainingStatusData": {
                "1": {"primaryTrainingDevice": False, "trainingStatusFeedbackPhrase": "OTHER"},
                "2": {
                    "primaryTrainingDevice": True,
                    "trainingStatus": 4,
                    "trainingStatusFeedbackPhrase": "MAINTAINING_2",
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": 573,
                        "dailyTrainingLoadChronic": 590,
                        "dailyAcuteChronicWorkloadRatio": 0.9,
                        "acwrPercent": 38,
                    },
                },
            }
        }
        client.get_max_metrics.return_value = [
            {"generic": None, "cycling": {"vo2MaxPreciseValue": 54.4, "vo2MaxValue": 54}}
        ]
        client.get_training_four_week_load_balance.return_value = {
            "metricsTrainingLoadBalanceDTOMap": {
                "2": {
                    "primaryTrainingDevice": True,
                    "monthlyLoadAerobicLow": 967.12445,
                    "monthlyLoadAerobicHigh": 1143.1078,
                    "monthlyLoadAnaerobic": 112.59972,
                }
            }
        }
        client.get_running_tolerance.side_effect = RuntimeError("down")
        bodies: list[bytes] = []

        def store(_connection: object, **kwargs: object) -> dict:
            body = kwargs["body"]
            assert isinstance(body, bytes)
            bodies.append(body)
            record = _raw("day", None, kwargs["day"] if isinstance(kwargs["day"], str) else None)
            record["stored"] = True
            return record

        with _archive_patches(client, activity_ids=set(), days={"2026-10-15"}):
            with patch("app.garmin.archive._store_bytes", side_effect=store):
                with patch("app.garmin.archive.write_day_metrics") as write:
                    result = archive_period("2026-10-15", "2026-10-15")

        client.get_sleep_data.assert_not_called()
        client.get_heart_rates.assert_not_called()
        client.get_hrv_data.assert_called_once_with("2026-10-15")
        client.get_running_tolerance.assert_called_once_with("2026-10-15", "2026-10-15", "daily")
        self.assertEqual(result["downloaded_day_count"], 0)
        stored = json.loads(bodies[0])
        self.assertNotIn("hrvReadings", stored["hrv"])
        self.assertEqual(stored["hrv"]["hrvSummary"]["status"], "UNBALANCED")
        fields = write.call_args.args[2]
        self.assertEqual(fields["hrv_status"], "UNBALANCED")
        self.assertEqual(fields["readiness_score"], 76.0)
        self.assertEqual(fields["readiness_level"], "HIGH")
        self.assertEqual(fields["training_status"], "MAINTAINING_2")
        self.assertEqual(fields["garmin_load_acute"], 573.0)
        self.assertEqual(fields["garmin_load_chronic"], 590.0)
        self.assertEqual(fields["garmin_acwr"], 0.9)
        self.assertNotIn("vo2max_generic", fields)
        self.assertEqual(fields["vo2max_cycling"], 54.4)
        self.assertEqual(fields["monthly_load_aerobic_low"], 967.12445)
        self.assertEqual(fields["monthly_load_aerobic_high"], 1143.1078)
        self.assertEqual(fields["monthly_load_anaerobic"], 112.59972)
        self.assertNotIn("running_tolerance", fields)
        self.assertNotIn("running_impact_load", fields)

    def test_period_fetches_sleep_again_when_the_stored_night_is_empty(self) -> None:
        client = _garmin_client([])
        client.get_activities_by_date.return_value = []
        client.get_sleep_data.return_value = {"dailySleepDTO": {"sleepTimeSeconds": 25000}}
        client.get_heart_rates.return_value = {"restingHeartRate": 40}
        empty_night = json.dumps(
            {
                "sleep": {"dailySleepDTO": {"sleepTimeSeconds": None}},
                "heart_rate": {"restingHeartRate": None, "calendarDate": "2026-10-17"},
            }
        ).encode()
        with _archive_patches(client, activity_ids=set(), days={"2026-10-17"}):
            with patch("app.garmin.archive.get_private", return_value=empty_night):
                with patch("app.garmin.archive.write_day_metrics") as write:
                    result = archive_period("2026-10-17", "2026-10-17")
        client.get_sleep_data.assert_called_once_with("2026-10-17")
        client.get_heart_rates.assert_called_once_with("2026-10-17")
        self.assertEqual(result["downloaded_day_count"], 1)
        self.assertEqual(write.call_args.args[2]["sleep_duration_sec"], 25000.0)
        self.assertEqual(write.call_args.args[2]["resting_hr"], 40.0)

    def test_refresh_rewrites_stored_days_without_activity_downloads(self) -> None:
        client = _garmin_client([])
        with _archive_patches(client, activity_ids=set(), days=set()):
            with patch("app.garmin.archive.stored_days", return_value=["2026-10-14", "2026-10-15"]):
                with patch("app.garmin.archive._archive_day", return_value=0) as archive_day:
                    result = refresh_stored_days()
        client.get_activities_by_date.assert_not_called()
        client.download_activity.assert_not_called()
        self.assertEqual(
            [call.args[2] for call in archive_day.call_args_list],
            ["2026-10-14", "2026-10-15"],
        )
        self.assertEqual(result["day_count"], 2)
        self.assertEqual(result["refreshed_count"], 2)
        self.assertEqual(result["failed"], [])


def _garmin_client(activities: list[dict]) -> MagicMock:
    client = MagicMock()
    client.profile_id = 51300124
    client.client.dumps.return_value = "{}"
    client.get_activities.return_value = activities
    client.download_activity.return_value = b"zip"
    client.get_sleep_data.return_value = {"dailySleepDTO": {}}
    client.get_heart_rates.return_value = {"restingHeartRate": 48}
    client.get_hrv_data.return_value = {"hrvSummary": {"status": "BALANCED"}, "hrvReadings": [1]}
    client.get_training_readiness.return_value = []
    client.get_daily_training_status.return_value = {"latestTrainingStatusData": {}}
    client.get_max_metrics.return_value = []
    client.get_training_four_week_load_balance.return_value = {"metricsTrainingLoadBalanceDTOMap": {}}
    client.get_running_tolerance.return_value = []
    return client


def _raw(kind: str, activity_id: int | None, day: str | None) -> dict:
    return {
        "kind": kind,
        "garmin_activity_id": activity_id,
        "day": day,
        "source_format": "zip" if kind == "activity" else "json",
        "source_path": f"garmin/1/{kind}/stored",
        "source_sha256": f"sha-{kind}-{activity_id or day}",
        "byte_size": 4,
    }


class _archive_patches:
    def __init__(self, client: MagicMock, activity_ids: set[int], days: set[str]) -> None:
        self.client = client
        self.activity_ids = activity_ids
        self.days = days
        self._stack = None

    def __enter__(self) -> None:
        from contextlib import ExitStack

        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False

        def find_activity(_connection: object, activity_id: int) -> dict | None:
            if activity_id in self.activity_ids:
                return _raw("activity", activity_id, None)
            return None

        def find_day(_connection: object, day: str) -> dict | None:
            if day in self.days:
                return _raw("day", None, day)
            return None

        def store(_connection: object, **kwargs: object) -> dict:
            return {
                "kind": kwargs["kind"],
                "garmin_activity_id": kwargs["garmin_activity_id"],
                "day": kwargs["day"],
                "source_format": kwargs["source_format"],
                "source_path": "garmin/1/new",
                "source_sha256": "new",
                "byte_size": 3,
                "stored": True,
            }

        stack = ExitStack()
        stack.enter_context(
            patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key"}, clear=False)
        )
        stack.enter_context(patch("app.garmin.archive._login", return_value=self.client))
        stack.enter_context(patch("app.garmin.archive.connect", return_value=connection))
        stack.enter_context(patch("app.garmin.archive.ensure_schema"))
        stack.enter_context(patch("app.garmin.archive.load_token", return_value=None))
        stack.enter_context(patch("app.garmin.archive.save_token"))
        stack.enter_context(
            patch("app.garmin.archive.find_activity_raw_object", side_effect=find_activity)
        )
        stack.enter_context(patch("app.garmin.archive.find_day_raw_object", side_effect=find_day))
        stack.enter_context(patch("app.garmin.archive._store_bytes", side_effect=store))
        stack.enter_context(
            patch(
                "app.garmin.archive.get_private",
                return_value=json.dumps(
                    {
                        "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 1}},
                        "heart_rate": {"restingHeartRate": 48},
                    }
                ).encode(),
            )
        )
        self._stack = stack
        stack.__enter__()
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._stack is not None:
            self._stack.__exit__(exc_type, exc, tb)


class BlobRequestTest(unittest.TestCase):
    def test_put_uses_a_private_blob_request(self) -> None:
        body = json.dumps({"pathname": "garmin/1/activity/9/abc.zip"}).encode()
        response = MagicMock()
        response.read.return_value = body
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_store123_secret"}, clear=False):
            with patch("app.storage.blob.urllib.request.urlopen", return_value=response) as urlopen:
                pathname = put_private("garmin/1/activity/9/abc.zip", b"zip", "application/zip")
        self.assertEqual(pathname, "garmin/1/activity/9/abc.zip")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("X-vercel-blob-access"), "private")
        self.assertEqual(request.get_header("X-vercel-blob-store-id"), "store123")
        self.assertIn("pathname=garmin%2F1%2Factivity%2F9%2Fabc.zip", request.full_url)
        self.assertIsInstance(request.data, bytes)
        self.assertNotIsInstance(request.data, io.StringIO)
