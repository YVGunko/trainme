import unittest
from datetime import date
from unittest.mock import MagicMock

from app.history_summary import RAW_DAYS, split_history, week_start, weekly_summary
from app.storage.db import load_activity_history


class WeekStartTest(unittest.TestCase):
    def test_a_monday_stays_on_itself(self) -> None:
        self.assertEqual(week_start("2026-11-16"), "2026-11-16")

    def test_a_sunday_goes_back_to_monday(self) -> None:
        self.assertEqual(week_start("2026-11-22"), "2026-11-16")

    def test_a_midweek_day_goes_back_to_monday(self) -> None:
        self.assertEqual(week_start("2026-11-18"), "2026-11-16")


class SplitHistoryTest(unittest.TestCase):
    def test_splits_at_the_raw_window(self) -> None:
        today = date(2026, 11, 18)
        rows = [
            {"day": "2026-11-18"},
            {"day": "2026-11-05"},
            {"day": "2026-11-04"},
            {"day": "2026-11-03"},
            {"day": "2025-12-01"},
        ]
        recent, older = split_history(rows, today)
        # The cutoff is today minus 14 days, so the 4th still falls inside it.
        self.assertEqual(
            [row["day"] for row in recent], ["2026-11-18", "2026-11-05", "2026-11-04"]
        )
        self.assertEqual([row["day"] for row in older], ["2026-11-03", "2025-12-01"])

    def test_the_window_is_fourteen_days(self) -> None:
        self.assertEqual(RAW_DAYS, 14)

    def test_a_row_without_a_usable_day_is_dropped(self) -> None:
        recent, older = split_history(
            [{"day": None}, {"day": "not a date"}, {"day": "2026-11-18"}],
            date(2026, 11, 18),
        )
        self.assertEqual(len(recent), 1)
        self.assertEqual(older, [])


class WeeklySummaryTest(unittest.TestCase):
    def test_totals_group_by_week_oldest_first(self) -> None:
        rows = [
            {"day": "2026-11-18", "sport": "cycling", "duration_sec": 3600.0, "training_load": 50.0},
            {"day": "2026-11-16", "sport": "cycling", "duration_sec": 1800.0, "training_load": 20.0},
            {"day": "2026-11-09", "sport": "running", "duration_sec": 2700.0, "training_load": 30.0},
        ]
        weeks = weekly_summary(rows)
        self.assertEqual([week["week"] for week in weeks], ["2026-11-09", "2026-11-16"])
        first, second = weeks
        self.assertEqual(first["sessions"], 1)
        self.assertEqual(first["minutes"], 45.0)
        self.assertEqual(first["by_sport_minutes"], {"running": 45.0})
        self.assertEqual(second["sessions"], 2)
        self.assertEqual(second["minutes"], 90.0)
        self.assertEqual(second["load"], 70.0)
        self.assertEqual(second["by_sport_minutes"], {"cycling": 90.0})

    def test_missing_numbers_do_not_break_a_week(self) -> None:
        weeks = weekly_summary([{"day": "2026-11-16", "sport": None}])
        self.assertEqual(weeks[0]["sessions"], 1)
        self.assertEqual(weeks[0]["minutes"], 0.0)
        self.assertEqual(weeks[0]["load"], 0.0)
        self.assertEqual(weeks[0]["by_sport_minutes"], {"other": 0.0})

    def test_a_sport_given_twice_accumulates(self) -> None:
        rows = [
            {"day": "2026-11-16", "sport": "running", "duration_sec": 600.0},
            {"day": "2026-11-17", "sport": "running", "duration_sec": 600.0},
        ]
        weeks = weekly_summary(rows)
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0]["by_sport_minutes"], {"running": 20.0})

    def test_an_empty_list_gives_an_empty_summary(self) -> None:
        self.assertEqual(weekly_summary([]), [])


class HistoryOrderTest(unittest.TestCase):
    """The payload feeds a model that reads it as a timeline."""

    def test_the_query_orders_oldest_first(self) -> None:
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        load_activity_history(connection, "2025-11-18", "2026-11-18", 400)
        sql = " ".join(connection.execute.call_args.args[0].split()).lower()
        self.assertIn("order by start_local asc", sql)
        # A LIMIT over a descending list would keep the oldest rows and drop the
        # newest, which is the opposite of what a coach needs.
        self.assertNotIn("order by start_local desc", sql)


if __name__ == "__main__":
    unittest.main()
