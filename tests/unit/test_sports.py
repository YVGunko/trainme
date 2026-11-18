import unittest

from app.sports import SPORTS, SportNameError, is_programmable, to_sport


class ToSportTest(unittest.TestCase):
    def test_the_five_names_pass_through(self) -> None:
        for sport in SPORTS:
            with self.subTest(sport=sport):
                self.assertEqual(to_sport(sport), sport)

    def test_garmin_names_fold_into_the_five(self) -> None:
        cases = {
            "road_biking": "cycling",
            "indoor_cycling": "cycling",
            "gravel_cycling": "cycling",
            "mountain_biking": "cycling",
            "virtual_ride": "cycling",
            "indoor_running": "running",
            "trail_running": "running",
            "treadmill_running": "running",
            "indoor_cardio": "strength_training",
            "hiit": "strength_training",
            "pilates": "mobility",
            "stretching": "mobility",
        }
        for garmin, expected in cases.items():
            with self.subTest(garmin=garmin):
                self.assertEqual(to_sport(garmin), expected)

    def test_a_version_suffix_is_ignored(self) -> None:
        # Garmin reports stand_up_paddleboarding_v2 in the real account.
        self.assertEqual(to_sport("stand_up_paddleboarding_v2"), "other")
        self.assertEqual(to_sport("cycling_v2"), "cycling")

    def test_an_unprogrammable_sport_is_other_not_an_error(self) -> None:
        for name in ("resort_skiing", "walking", "golf", "swimming"):
            with self.subTest(name=name):
                self.assertEqual(to_sport(name), "other")

    def test_case_and_spacing_do_not_matter(self) -> None:
        self.assertEqual(to_sport("  Road_Biking  "), "cycling")
        self.assertEqual(to_sport("RUNNING"), "running")

    def test_a_missing_sport_is_other(self) -> None:
        self.assertEqual(to_sport(None), "other")
        self.assertEqual(to_sport(""), "other")

    def test_a_non_string_is_reported(self) -> None:
        for value in (5, [], {}, True):
            with self.subTest(value=value):
                with self.assertRaises(SportNameError):
                    to_sport(value)

    def test_is_programmable_matches_the_five(self) -> None:
        self.assertTrue(is_programmable("road_biking"))
        self.assertTrue(is_programmable("strength_training"))
        self.assertFalse(is_programmable("resort_skiing"))


if __name__ == "__main__":
    unittest.main()
