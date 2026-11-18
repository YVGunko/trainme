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
        self.assertEqual(context["history"], [])
        self.assertEqual(context["recent_days"], [])
        self.assertEqual(context["wellness"], [])

    def test_the_profile_comes_first(self) -> None:
        # Prompt caching bills a stable prefix at the cached rate, so the order
        # of the keys is a billing decision, not a cosmetic one.
        context = self._build(profile={"notes": "hamstring", "avoided_sports": ["running"]})
        self.assertEqual(list(context)[0], "profile")
        self.assertEqual(context["profile"]["notes"], "hamstring")

    def test_history_and_days_are_passed_through_unchanged(self) -> None:
        history = [{"day": "2026-11-16", "sport": "cycling"}]
        days = [{"date": "2026-11-17", "resting_hr": 48}]
        wellness = [{"date": "2026-11-17", "injury": 2}]
        context = self._build(history=history, days=days, wellness=wellness)
        self.assertEqual(context["history"], history)
        self.assertEqual(context["recent_days"], days)
        self.assertEqual(context["wellness"], wellness)

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


class CoverageTest(unittest.TestCase):
    def test_reports_counts_and_the_history_range(self) -> None:
        context = {
            "today": "2026-11-18",
            "profile": {"notes": "hamstring", "avoided_sports": ["running"]},
            "recent_days": [{"date": "2026-11-17"}],
            "wellness": [{"date": "2026-11-17"}],
            "history": [
                {"day": "2026-01-02"},
                {"day": "2026-11-16"},
            ],
        }
        report = coverage(context)
        self.assertEqual(report["history_count"], 2)
        self.assertEqual(report["history_first_day"], "2026-01-02")
        self.assertEqual(report["history_last_day"], "2026-11-16")
        self.assertEqual(report["detail_day_count"], 1)
        self.assertTrue(report["profile_has_notes"])
        self.assertEqual(report["avoided_sports"], ["running"])

    def test_empty_history_is_reported_as_empty_not_as_no_training(self) -> None:
        report = coverage({"today": "2026-11-18", "history": []})
        self.assertEqual(report["history_count"], 0)
        self.assertIsNone(report["history_first_day"])
        self.assertFalse(report["profile_has_notes"])


class ContextRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            self.assertEqual(client.get("/context").status_code, 401)

    def test_returns_the_context_and_its_coverage(self) -> None:
        client = TestClient(app)
        context = {"today": "2026-11-18", "profile": {}, "history": [], "recent_days": [], "wellness": []}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.build_context", return_value=context):
                response = client.get("/context", headers={"Authorization": "Bearer expected"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["context"], context)
        self.assertEqual(body["coverage"]["history_count"], 0)


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
