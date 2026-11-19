import unittest
from unittest.mock import MagicMock

from app.garmin.evaluation import FEEL_VALUES, read_evaluation


class EffortTest(unittest.TestCase):
    def test_garmin_stores_effort_times_ten(self) -> None:
        # 70 in the response is the 7 the athlete entered.
        self.assertEqual(read_evaluation({"summaryDTO": {"directWorkoutRpe": 70}})["perceived_effort"], 7)

    def test_the_whole_range_reads_back(self) -> None:
        for stored, expected in ((10, 1), (50, 5), (100, 10)):
            with self.subTest(stored=stored):
                found = read_evaluation({"summaryDTO": {"directWorkoutRpe": stored}})
                self.assertEqual(found["perceived_effort"], expected)

    def test_an_impossible_effort_is_dropped(self) -> None:
        # A rating outside 1-10 would be a bad read, not a real answer.
        for value in (0, 5, 200, -10):
            with self.subTest(value=value):
                found = read_evaluation({"summaryDTO": {"directWorkoutRpe": value}})
                self.assertIsNone(found["perceived_effort"])

    def test_an_unrated_session_stays_empty(self) -> None:
        found = read_evaluation({"summaryDTO": {}})
        self.assertIsNone(found["perceived_effort"])
        self.assertIsNone(found["feel"])
        self.assertIsNone(found["activity_note"])


class FeelTest(unittest.TestCase):
    def test_the_five_points_read_back(self) -> None:
        for value in FEEL_VALUES:
            with self.subTest(value=value):
                found = read_evaluation({"summaryDTO": {"directWorkoutFeel": value}})
                self.assertEqual(found["feel"], value)

    def test_a_value_garmin_cannot_display_is_dropped(self) -> None:
        found = read_evaluation({"summaryDTO": {"directWorkoutFeel": 30}})
        self.assertIsNone(found["feel"])


class ActivityNoteTest(unittest.TestCase):
    def test_a_description_is_kept(self) -> None:
        found = read_evaluation({"description": "  колено ныло  "})
        self.assertEqual(found["activity_note"], "колено ныло")

    def test_a_description_inside_the_summary_is_found_too(self) -> None:
        found = read_evaluation({"summaryDTO": {"description": "тяжело"}})
        self.assertEqual(found["activity_note"], "тяжело")

    def test_a_blank_description_is_ignored(self) -> None:
        self.assertIsNone(read_evaluation({"description": "   "})["activity_note"])


class ShapeTest(unittest.TestCase):
    def test_an_unexpected_response_does_not_raise(self) -> None:
        # The evaluation is a bonus; a strange shape must not lose the import.
        for payload in (None, {}, [], "text", 5, {"summaryDTO": None}, {"summaryDTO": []}):
            with self.subTest(payload=payload):
                found = read_evaluation(payload)
                self.assertIsNone(found["perceived_effort"])
                self.assertIsNone(found["feel"])

    def test_a_long_note_is_capped(self) -> None:
        found = read_evaluation({"description": "x" * 10000})
        self.assertEqual(len(found["activity_note"]), 4000)


if __name__ == "__main__":
    unittest.main()
