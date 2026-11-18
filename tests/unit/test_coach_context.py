import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.coach_context import build_context, coverage
from app.main import app


class BuildContextTest(unittest.TestCase):
    def _build(self, profile=None, history=None, days=None, wellness=None):
        with patch("app.coach_context.connect") as connect:
            connect.return_value.__enter__.return_value = MagicMock()
            with patch("app.coach_context.ensure_schema"):
                with patch("app.coach_context.load_athlete_profile", return_value=profile):
                    with patch(
                        "app.coach_context.load_activity_history",
                        return_value=history or [],
                    ):
                        with patch("app.coach_context.load_recent_days", return_value=days or []):
                            with patch(
                                "app.coach_context.load_subjective_days",
                                return_value=wellness or [],
                            ):
                                return build_context(date(2026, 11, 18))

    def test_an_empty_database_still_builds_a_context(self) -> None:
        context = self._build()
        self.assertEqual(context["today"], "2026-11-18")
        self.assertEqual(context["profile"], {"notes": None, "avoided_sports": []})
        self.assertEqual(context["recent_activities"], [])
        self.assertEqual(context["weekly_totals"], [])
        self.assertEqual(context["recent_days"], [])
        self.assertEqual(context["wellness"], [])

    def test_the_profile_comes_first(self) -> None:
        # Prompt caching bills a stable prefix at the cached rate, so the order
        # of the keys is a billing decision, not a cosmetic one.
        context = self._build(profile={"notes": "hamstring", "avoided_sports": ["running"]})
        self.assertEqual(list(context)[0], "profile")
        self.assertEqual(context["profile"]["notes"], "hamstring")

    def test_history_and_days_are_passed_through_unchanged(self) -> None:
        history = [
            {"day": "2026-08-03", "sport": "cycling", "duration_sec": 3600.0, "training_load": 50.0},
        ]
        days = [{"date": "2026-11-17", "resting_hr": 48}]
        wellness = [{"date": "2026-11-17", "injury": 2}]
        context = self._build(history=history, days=days, wellness=wellness)
        # Old activities become weekly totals, not raw rows.
        self.assertEqual(len(context["weekly_totals"]), 1)
        self.assertEqual(context["weekly_totals"][0]["week"], "2026-08-03")
        self.assertEqual(context["weekly_totals"][0]["sessions"], 1)
        self.assertEqual(context["recent_activities"], [])
        self.assertEqual(context["recent_days"], days)
        self.assertEqual(context["wellness"], wellness)

    def test_recent_activities_stay_raw_for_a_fortnight(self) -> None:
        history = [
            {"day": "2026-11-17", "sport": "cycling", "duration_sec": 3600.0,
             "distance_m": 30000.0, "avg_hr": 130.0, "training_load": 50.0},
            {"day": "2026-11-01", "sport": "running", "duration_sec": 1800.0, "training_load": 20.0},
        ]
        context = self._build(history=history)
        self.assertEqual(len(context["recent_activities"]), 1)
        recent = context["recent_activities"][0]
        self.assertEqual(recent["day"], "2026-11-17")
        self.assertEqual(recent["minutes"], 60.0)
        self.assertEqual(recent["km"], 30.0)
        self.assertEqual(recent["avg_hr"], 130.0)
        self.assertEqual(len(context["weekly_totals"]), 1)

    def test_history_lookback_spans_a_year(self) -> None:
        with patch("app.coach_context.connect") as connect:
            connect.return_value.__enter__.return_value = MagicMock()
            with patch("app.coach_context.ensure_schema"):
                with patch("app.coach_context.load_athlete_profile", return_value=None):
                    with patch(
                        "app.coach_context.load_activity_history", return_value=[]
                    ) as history:
                        with patch("app.coach_context.load_recent_days", return_value=[]):
                            with patch(
                                "app.coach_context.load_subjective_days", return_value=[]
                            ):
                                build_context(date(2026, 11, 18))
        start, end, _limit = history.call_args.args[1:]
        self.assertEqual(end, "2026-11-18")
        self.assertEqual(start, "2025-11-18")

    def test_the_detail_window_covers_exactly_its_day_count(self) -> None:
        with patch("app.coach_context.connect") as connect:
            connect.return_value.__enter__.return_value = MagicMock()
            with patch("app.coach_context.ensure_schema"):
                with patch("app.coach_context.load_athlete_profile", return_value=None):
                    with patch("app.coach_context.load_activity_history", return_value=[]):
                        with patch("app.coach_context.load_recent_days", return_value=[]) as days:
                            with patch(
                                "app.coach_context.load_subjective_days", return_value=[]
                            ):
                                build_context(date(2026, 11, 18))
        start, end = days.call_args.args[1:]
        span = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
        # Both ends are inclusive, so the span must equal the promise.
        self.assertEqual(span, 28)
class CoverageTest(unittest.TestCase):
    def test_reports_counts_and_the_week_range(self) -> None:
        context = {
            "today": "2026-11-18",
            "profile": {"notes": "hamstring", "avoided_sports": ["running"]},
            "recent_days": [{"date": "2026-11-17"}],
            "wellness": [{"date": "2026-11-17"}],
            "recent_activities": [{"day": "2026-11-16"}],
            "weekly_totals": [
                {"week": "2026-01-05", "sessions": 3},
                {"week": "2026-11-02", "sessions": 4},
            ],
        }
        report = coverage(context)
        self.assertEqual(report["raw_activity_count"], 1)
        self.assertEqual(report["week_count"], 2)
        self.assertEqual(report["weeks_first"], "2026-01-05")
        self.assertEqual(report["weeks_last"], "2026-11-02")
        self.assertEqual(report["detail_day_count"], 1)
        self.assertTrue(report["profile_has_notes"])
        self.assertEqual(report["avoided_sports"], ["running"])

    def test_empty_history_is_reported_as_empty_not_as_no_training(self) -> None:
        report = coverage({"today": "2026-11-18", "recent_activities": [], "weekly_totals": []})
        self.assertEqual(report["raw_activity_count"], 0)
        self.assertEqual(report["week_count"], 0)
        self.assertIsNone(report["weeks_first"])
        self.assertFalse(report["profile_has_notes"])


class ContextRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            self.assertEqual(client.get("/context").status_code, 401)

    def test_returns_the_context_and_its_coverage(self) -> None:
        client = TestClient(app)
        context = {
            "today": "2026-11-18",
            "profile": {},
            "history": [],
            "recent_days": [],
            "wellness": [],
        }
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.build_context", return_value=context):
                response = client.get("/context", headers={"Authorization": "Bearer expected"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["context"], context)
        self.assertEqual(body["coverage"]["week_count"], 0)

    def test_a_failure_names_its_class_so_it_can_be_diagnosed(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch(
                "app.main.build_context",
                side_effect=RuntimeError("boom"),
            ):
                response = client.get("/context", headers={"Authorization": "Bearer expected"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("RuntimeError", response.json()["detail"])

    def test_a_missing_database_is_reported_as_unconfigured(self) -> None:
        from app.storage.db import DatabaseNotConfigured

        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.build_context", side_effect=DatabaseNotConfigured()):
                response = client.get("/context", headers={"Authorization": "Bearer expected"})
        self.assertEqual(response.status_code, 503)


class NoteNeverLeavesTest(unittest.TestCase):
    """The wellness note is written for the athlete, so it must not be queried."""

    def test_load_subjective_days_does_not_select_the_note(self) -> None:
        from app.storage.db import load_subjective_days

        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        load_subjective_days(connection, "2026-01-01", "2026-11-18")
        sql = " ".join(connection.execute.call_args.args[0].split()).lower()
        select_part = sql.split("from subjective_log")[0]
        self.assertNotIn("note", select_part)
        for field in ("fatigue", "soreness", "injury", "illness"):
            self.assertIn(field, select_part)

    def test_a_stored_note_cannot_reach_the_context(self) -> None:
        # Even if a row carried a note, the reader asks for named columns only,
        # so the value can never appear in the payload.
        from app.storage.db import load_subjective_days

        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = [
            ("2026-11-18", 1, 2, 3, 4, 1, 2, 3, 4),
        ]
        rows = load_subjective_days(connection, "2026-11-18", "2026-11-18")
        self.assertNotIn("note", rows[0])
        self.assertEqual(rows[0]["injury"], 3)
