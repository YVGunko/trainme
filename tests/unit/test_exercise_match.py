import unittest

from app.ai.exercise_match import (
    AMBIGUOUS,
    CLOSEST,
    EXACT,
    MISSING,
    describe_candidates,
    match_exercise,
)


class ExactMatchTest(unittest.TestCase):
    def test_a_catalog_name_is_found_exactly(self) -> None:
        match = match_exercise("Romanian Deadlift")
        self.assertEqual(match.outcome, EXACT)
        self.assertEqual(match.entry["name"], "Romanian Deadlift")
        self.assertTrue(match.settled)
        self.assertFalse(match.needs_question)

    def test_case_and_punctuation_do_not_matter(self) -> None:
        match = match_exercise("  goblet   squat ")
        self.assertTrue(match.settled)
        self.assertEqual(match.entry["name"], "Goblet Squat")

    def test_a_hyphenated_name_is_matched_however_it_is_typed(self) -> None:
        # The model writes "Step Up"; the catalog holds "Step-up".
        for typed in ("Step Up", "Step-up", "step up"):
            with self.subTest(typed=typed):
                match = match_exercise(typed)
                self.assertTrue(match.settled, typed)
                self.assertEqual(match.entry["name"], "Step-up")


class ClosestMatchTest(unittest.TestCase):
    def test_the_shortest_containing_name_wins_when_it_is_alone(self) -> None:
        match = match_exercise("Hip Abduction")
        self.assertEqual(match.outcome, CLOSEST)
        self.assertEqual(match.entry["name"], "Standing Hip Abduction")


class AmbiguousMatchTest(unittest.TestCase):
    def test_two_equally_short_names_are_offered_as_candidates(self) -> None:
        match = match_exercise("Glute Bridge")
        self.assertEqual(match.outcome, AMBIGUOUS)
        self.assertFalse(match.settled)
        self.assertTrue(match.needs_question)
        names = describe_candidates(match)
        self.assertIn("Banded Glute Bridge", names)
        self.assertIn("Suspension Glute Bridge", names)

    def test_candidates_are_shortest_first(self) -> None:
        match = match_exercise("Bulgarian Split Squat")
        names = describe_candidates(match)
        lengths = [len(name) for name in names]
        self.assertEqual(lengths, sorted(lengths))

    def test_the_candidate_list_is_bounded(self) -> None:
        match = match_exercise("Back Extension")
        self.assertLessEqual(len(describe_candidates(match, limit=3)), 3)


class MissingMatchTest(unittest.TestCase):
    def test_a_movement_the_catalog_lacks_is_reported_missing(self) -> None:
        # Named deliberately: this is a good hamstring exercise Garmin does not
        # hold, so the caller must decide rather than the matcher inventing one.
        match = match_exercise("Nordic Hamstring Curl")
        self.assertEqual(match.outcome, MISSING)
        self.assertIsNone(match.entry)
        self.assertEqual(match.candidates, [])
        self.assertTrue(match.needs_question)

    def test_a_missing_name_still_offers_close_names(self) -> None:
        # "Side-Lying Hip Abduction" is not in the catalog, but two of its words
        # point at real entries, and offering them lets the coach choose.
        match = match_exercise("Side-Lying Hip Abduction")
        self.assertEqual(match.outcome, MISSING)
        self.assertIsNone(match.entry)
        names = describe_candidates(match)
        self.assertTrue(names)
        self.assertTrue(any("Abduction" in name for name in names))

    def test_one_generic_word_does_not_offer_a_crowd(self) -> None:
        # "Pallof Press" would match every press in the catalog if a single
        # shared word were enough, and there is no Pallof press here.
        for name in ("Pallof Press", "Hip Hinge", "Bird Dog", "Clamshell"):
            with self.subTest(name=name):
                match = match_exercise(name)
                self.assertEqual(match.outcome, MISSING)
                self.assertEqual(match.candidates, [])

    def test_empty_and_non_string_input_is_missing(self) -> None:
        for value in ("", "   ", None, 5, []):
            with self.subTest(value=value):
                self.assertEqual(match_exercise(value).outcome, MISSING)


class PropertyTest(unittest.TestCase):
    def test_a_settled_match_never_needs_a_question(self) -> None:
        for name in ("Plank", "Squat", "Row", "Dead Bug", "Hip Abduction", "Face Pull"):
            with self.subTest(name=name):
                match = match_exercise(name)
                if match.settled:
                    self.assertFalse(match.needs_question)
                else:
                    self.assertTrue(match.needs_question)

    def test_an_ambiguous_match_always_offers_candidates(self) -> None:
        for name in ("Glute Bridge", "Hip Thrust", "Overhead Press"):
            with self.subTest(name=name):
                match = match_exercise(name)
                if match.outcome == AMBIGUOUS:
                    self.assertTrue(match.candidates)


if __name__ == "__main__":
    unittest.main()
