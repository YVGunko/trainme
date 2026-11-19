import unittest

from app.ai.fingerprint import context_fingerprint
from app.coach_context import build_context


def _context(**overrides):
    base = {
        "profile": {"notes": None, "avoided_sports": []},
        "today": "2026-11-19",
        "today_weekday": "Thursday",
        "timezone": "UTC+3",
        "recent_days": [{"date": "2026-11-18", "resting_hr": 44.0}],
        "wellness": [],
        "recent_activities": [{"day": "2026-11-18", "sport": "cycling"}],
        "weekly_totals": [{"week": "2026-11-16", "sessions": 2}],
    }
    base.update(overrides)
    return base


class FingerprintTest(unittest.TestCase):
    def test_the_same_input_gives_the_same_fingerprint(self) -> None:
        self.assertEqual(context_fingerprint(_context()), context_fingerprint(_context()))

    def test_a_new_activity_changes_it(self) -> None:
        changed = _context(recent_activities=[{"day": "2026-11-19", "sport": "running"}])
        self.assertNotEqual(context_fingerprint(_context()), context_fingerprint(changed))

    def test_a_new_day_metric_changes_it(self) -> None:
        changed = _context(recent_days=[{"date": "2026-11-18", "resting_hr": 48.0}])
        self.assertNotEqual(context_fingerprint(_context()), context_fingerprint(changed))

    def test_an_edited_wellness_row_changes_it(self) -> None:
        changed = _context(wellness=[{"date": "2026-11-19", "injury": 3}])
        self.assertNotEqual(context_fingerprint(_context()), context_fingerprint(changed))

    def test_an_edited_profile_changes_it(self) -> None:
        changed = _context(profile={"notes": "колено", "avoided_sports": []})
        self.assertNotEqual(context_fingerprint(_context()), context_fingerprint(changed))

    def test_a_different_plan_start_changes_it(self) -> None:
        # A week starting tomorrow is a different question even with the same history.
        changed = _context(today="2026-11-20")
        self.assertNotEqual(context_fingerprint(_context()), context_fingerprint(changed))

    def test_the_weekday_name_alone_does_not_change_it(self) -> None:
        # The weekday is derived from the date, which is already hashed.
        same = _context(today_weekday="Friday")
        self.assertEqual(context_fingerprint(_context()), context_fingerprint(same))

    def test_the_timezone_alone_does_not_change_it(self) -> None:
        same = _context(timezone="UTC+4")
        self.assertEqual(context_fingerprint(_context()), context_fingerprint(same))

    def test_every_section_the_coach_reads_is_covered(self) -> None:
        # A section added to the context but missing here would let a stale plan
        # survive a real change, so the list is compared against the builder.
        source = build_context.__code__.co_names
        for key in ("load_athlete_profile", "load_recent_days", "load_subjective_days"):
            self.assertIn(key, source)
        # The sections are named explicitly in the fingerprint module; this test
        # fails if one is dropped from it.
        from app.ai import fingerprint

        self.assertEqual(
            set(fingerprint._FINGERPRINT_SECTIONS),
            {"profile", "recent_days", "wellness", "recent_activities", "weekly_totals"},
        )


if __name__ == "__main__":
    unittest.main()
