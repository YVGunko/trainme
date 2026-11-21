import unittest

from app.profile_version import (
    garmin_view,
    normalize_garmin,
    profile_hash,
    with_garmin_profile,
    with_written_profile,
)


def _garmin() -> dict:
    return {
        "user_settings": {
            "userData": {
                "birthDate": "1988-04-02",
                "weight": 72500,
                "height": 181,
            }
        },
        "hr_zones": [
            {"sport": "RUNNING", "zone1Floor": 120, "zone2Floor": 140, "zone5Ceiling": 190}
        ],
        "power_zones": [
            {"sport": "CYCLING", "zone1Floor": 0, "zone2Floor": 150, "functionalThresholdPower": 250}
        ],
        "cycling_ftp": {"sport": "CYCLING", "functionalThresholdPower": 250},
    }


class ProfileHashTest(unittest.TestCase):
    def test_grams_and_kilograms_share_one_fingerprint(self) -> None:
        grams = normalize_garmin(_garmin())
        kilos = normalize_garmin(
            {
                **_garmin(),
                "user_settings": {"userData": {"birthDate": "1988-04-02", "weight": 72.5, "height": 181.0}},
            }
        )
        self.assertEqual(grams["weight_kg"], 72.5)
        self.assertEqual(profile_hash({**grams, "notes": None, "avoided_sports": []}), profile_hash({**kilos, "notes": None, "avoided_sports": []}))

    def test_zone_sports_are_ordered_by_name(self) -> None:
        mixed = normalize_garmin(
            {
                **_garmin(),
                "hr_zones": [
                    {"sport": "RUNNING", "zone1Floor": 120, "zone2Floor": 140},
                    {"sport": "CYCLING", "zone1Floor": 90, "zone2Floor": 120},
                ],
            }
        )
        self.assertEqual([item["sport"] for item in mixed["hr_zones"]], ["CYCLING", "RUNNING"])


class ProfileVersionTest(unittest.TestCase):
    def test_the_same_text_does_not_open_a_new_version(self) -> None:
        garmin = normalize_garmin(_garmin())
        first = with_garmin_profile(None, garmin, "sha-1")
        self.assertIsNotNone(first)
        first["recorded_at"] = "2026-11-21T04:00:00+00:00"
        again = with_written_profile(first, first["notes"], first["avoided_sports"])
        self.assertIsNone(again)

    def test_a_note_keeps_the_garmin_fields(self) -> None:
        garmin = normalize_garmin(_garmin())
        current = with_garmin_profile(None, garmin, "sha-1")
        revised = with_written_profile(current, "колено", ["running"])
        self.assertEqual(revised["weight_kg"], 72.5)
        self.assertEqual(revised["cycling_ftp"], 250.0)
        self.assertEqual(revised["hr_zones"], garmin["hr_zones"])
        self.assertEqual(revised["notes"], "колено")
        self.assertEqual(revised["source_sha256"], "sha-1")
        self.assertNotEqual(revised["content_hash"], current["content_hash"])

    def test_a_garmin_change_keeps_the_note(self) -> None:
        garmin = normalize_garmin(_garmin())
        current = with_written_profile(None, "колено", ["yoga"])
        changed = normalize_garmin(
            {**_garmin(), "cycling_ftp": {"functionalThresholdPower": 260}}
        )
        revised = with_garmin_profile(current, changed, "sha-2")
        self.assertEqual(revised["notes"], "колено")
        self.assertEqual(revised["avoided_sports"], ["yoga"])
        self.assertEqual(revised["cycling_ftp"], 260.0)
        self.assertEqual(revised["source_sha256"], "sha-2")

    def test_an_unreadable_garmin_reply_is_not_a_profile(self) -> None:
        self.assertIsNone(normalize_garmin({"user_settings": ["nope"]}))

    def test_a_note_only_row_has_no_garmin_view(self) -> None:
        current = with_written_profile(None, "колено", [])
        self.assertIsNone(garmin_view(current))

    def test_garmin_view_keeps_the_stored_fields(self) -> None:
        current = with_garmin_profile(None, normalize_garmin(_garmin()), "sha-1")
        view = garmin_view(current)
        self.assertEqual(view["birth_date"], "1988-04-02")
        self.assertEqual(view["weight_kg"], 72.5)
        self.assertEqual(view["cycling_ftp"], 250.0)
        self.assertEqual(view["hr_zones"][0]["sport"], "RUNNING")


class GarminProfileReadTest(unittest.TestCase):
    def test_reads_the_four_current_profile_calls(self) -> None:
        from unittest.mock import MagicMock

        from app.garmin.profile import read_garmin_profile

        client = MagicMock()
        read_garmin_profile(client)
        client.get_user_profile.assert_called_once_with()
        client.get_heart_rate_zones.assert_called_once_with()
        client.get_power_zones.assert_called_once_with()
        client.get_cycling_ftp.assert_called_once_with()
