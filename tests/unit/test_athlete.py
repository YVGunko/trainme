import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from garminconnect import GarminConnectConnectionError

from app.garmin.history import (
    HistoryPeriodError,
    _history_row,
    import_history,
    parse_history_period,
)
from app.main import app
from app.profile import ProfileError, parse_profile


class ParseProfileTest(unittest.TestCase):
    def test_reads_notes_and_avoids(self) -> None:
        profile = parse_profile(
            {"notes": "  колено правое  ", "avoided_sports": ["running", "mobility"]}
        )
        self.assertEqual(profile["notes"], "колено правое")
        self.assertEqual(profile["avoided_sports"], ["running", "mobility"])

    def test_an_empty_profile_is_allowed(self) -> None:
        self.assertEqual(parse_profile({}), {"notes": None, "avoided_sports": []})

    def test_blank_notes_become_none(self) -> None:
        self.assertIsNone(parse_profile({"notes": "   "})["notes"])

    def test_unknown_sport_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            parse_profile({"avoided_sports": ["swimming"]})

    def test_a_sport_given_twice_is_stored_once(self) -> None:
        profile = parse_profile({"avoided_sports": ["running", "running"]})
        self.assertEqual(profile["avoided_sports"], ["running"])

    def test_unknown_field_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            parse_profile({"notes": "x", "weight": 70})

    def test_overlong_notes_are_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            parse_profile({"notes": "x" * 4001})

    def test_a_body_that_is_not_an_object_is_rejected(self) -> None:
        for body in (None, [], "text", 5):
            with self.subTest(body=body):
                with self.assertRaises(ProfileError):
                    parse_profile(body)

    def test_sports_must_be_a_list_of_known_names(self) -> None:
        with self.assertRaises(ProfileError):
            parse_profile({"avoided_sports": "running"})
        with self.assertRaises(ProfileError):
            parse_profile({"avoided_sports": [1]})


class ParseHistoryPeriodTest(unittest.TestCase):
    def test_accepts_a_year(self) -> None:
        start, end = parse_history_period("2025-11-18", "2026-11-18")
        self.assertEqual(end.toordinal() - start.toordinal(), 365)

    def test_rejects_a_mistyped_decade(self) -> None:
        with self.assertRaises(HistoryPeriodError):
            parse_history_period("2016-01-01", "2026-01-01")

    def test_rejects_a_reversed_period(self) -> None:
        with self.assertRaises(HistoryPeriodError):
            parse_history_period("2026-11-18", "2026-11-01")

    def test_rejects_a_bad_date(self) -> None:
        with self.assertRaises(HistoryPeriodError):
            parse_history_period("18.11.2026", "2026-11-18")


class HistoryRowTest(unittest.TestCase):
    def test_takes_only_the_summary_fields(self) -> None:
        row = _history_row(
            {
                "activityId": 123,
                "activityName": "Ride",
                "startTimeLocal": "2026-11-16T09:30:00.0",
                "activityType": {"typeKey": "cycling"},
                "duration": 5400.0,
                "distance": 42000.0,
                "averageHR": 138,
                "maxHR": 172,
                "calories": 900,
                "activityTrainingLoad": 78.5,
                "hrTimeInZone_1": 600,
            }
        )
        self.assertEqual(row["garmin_activity_id"], 123)
        self.assertEqual(row["day"], "2026-11-16")
        self.assertEqual(row["start_local"], "2026-11-16 09:30:00")
        self.assertEqual(row["sport"], "cycling")
        self.assertEqual(row["duration_sec"], 5400.0)
        self.assertEqual(row["training_load"], 78.5)
        # Zone seconds belong to the archive, not to the history summary.
        self.assertNotIn("hrTimeInZone_1", row)

    def test_missing_number_fields_stay_none(self) -> None:
        row = _history_row({"activityId": 1, "startTimeLocal": "2026-11-16T09:30:00.0"})
        self.assertIsNone(row["duration_sec"])
        self.assertIsNone(row["avg_hr"])

    def test_a_row_without_a_start_is_refused(self) -> None:
        from app.garmin.archive import ArchiveError

        with self.assertRaises(ArchiveError):
            _history_row({"activityId": 1})


class ImportHistoryTest(unittest.TestCase):
    def test_stores_the_summaries_and_counts_skips(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.get_activities_by_date.return_value = [
            {
                "activityId": 1,
                "startTimeLocal": "2026-11-16T09:30:00.0",
                "activityType": {"typeKey": "cycling"},
                "duration": 5400.0,
            },
            "not a dict",
            {"activityId": 2},
        ]
        with _patched_import(client):
            with patch("app.garmin.history.upsert_activity_history", return_value=2) as save:
                with patch("app.garmin.history.activity_history_count", return_value=2):
                    result = import_history("2025-11-18", "2026-11-18")
        self.assertEqual(result["activity_count"], 3)
        self.assertEqual(result["stored_count"], 2)
        self.assertEqual(result["skipped_count"], 2)
        self.assertEqual(len(save.call_args.args[1]), 1)
        client.get_activities_by_date.assert_called_once_with(
            "2025-11-18", "2026-11-18", sortorder="asc"
        )

    def test_no_fit_download_and_no_daily_read_happens(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.get_activities_by_date.return_value = []
        with _patched_import(client):
            with patch("app.garmin.history.upsert_activity_history", return_value=0):
                with patch("app.garmin.history.activity_history_count", return_value=0):
                    import_history("2026-01-01", "2026-11-18")
        client.download_activity.assert_not_called()
        client.get_sleep_data.assert_not_called()
        client.get_heart_rates.assert_not_called()
        client.get_hrv_data.assert_not_called()

    def test_a_bad_period_stops_before_login(self) -> None:
        with patch("app.garmin.history._login") as login:
            with self.assertRaises(HistoryPeriodError):
                import_history("2016-01-01", "2026-01-01")
        login.assert_not_called()

    def test_a_missing_encryption_key_is_reported(self) -> None:
        from app.storage.crypto import EncryptionKeyMissing

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EncryptionKeyMissing):
                import_history("2026-01-01", "2026-02-01")


class ProfileRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            self.assertEqual(client.get("/profile").status_code, 401)
            self.assertEqual(client.post("/profile", json={}).status_code, 401)

    def test_reads_the_profile(self) -> None:
        client = TestClient(app)
        summary = {"notes": None, "avoided_sports": []}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.read_profile", return_value=summary):
                response = client.get(
                    "/profile", headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)

    def test_a_bad_profile_is_a_bad_request(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.write_profile", side_effect=ProfileError("Unknown sport: swimming")):
                response = client.post(
                    "/profile",
                    json={"avoided_sports": ["swimming"]},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 400)
        self.assertIn("swimming", response.json()["detail"])


class HistoryRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/history", json={"start": "2026-01-01", "end": "2026-02-01"})
        self.assertEqual(response.status_code, 401)

    def test_rejects_a_missing_period(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/history", json={}, headers={"Authorization": "Bearer expected"}
            )
        self.assertEqual(response.status_code, 400)

    def test_returns_the_import_summary(self) -> None:
        client = TestClient(app)
        summary = {"start": "2025-11-18", "end": "2026-11-18", "stored_count": 180}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.import_history", return_value=summary) as run:
                response = client.post(
                    "/history",
                    json={"start": "2025-11-18", "end": "2026-11-18"},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)
        run.assert_called_once_with("2025-11-18", "2026-11-18")

    def test_a_garmin_failure_is_a_bad_gateway(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch(
                "app.main.import_history",
                side_effect=GarminConnectConnectionError("down"),
            ):
                response = client.post(
                    "/history",
                    json={"start": "2025-11-18", "end": "2026-11-18"},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 502)


class _FakeConnection:
    def __enter__(self) -> MagicMock:
        return MagicMock()

    def __exit__(self, *_: object) -> bool:
        return False


class _Stack:
    def __init__(self) -> None:
        self._patchers: list = []

    def enter_context(self, patcher: object) -> object:
        self._patchers.append(patcher)
        return patcher.__enter__()

    def __enter__(self) -> "_Stack":
        return self

    def __exit__(self, *_: object) -> bool:
        for patcher in reversed(self._patchers):
            patcher.__exit__(None, None, None)
        return False


def _patched_import(client: MagicMock) -> _Stack:
    stack = _Stack()
    stack.enter_context(patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key"}))
    stack.enter_context(patch("app.garmin.history.connect", return_value=_FakeConnection()))
    stack.enter_context(patch("app.garmin.history.ensure_schema"))
    stack.enter_context(patch("app.garmin.history.load_token", return_value="saved"))
    stack.enter_context(patch("app.garmin.history._login", return_value=client))
    stack.enter_context(patch("app.garmin.history.save_token"))
    return stack
