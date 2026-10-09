import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.garmin.client import summarize_activity
from app.main import app


class SummarizeActivityTest(unittest.TestCase):
    def test_keeps_only_summary_fields(self) -> None:
        summary = summarize_activity(
            {
                "activityId": 42,
                "activityName": "Morning",
                "activityType": {"typeKey": "cycling"},
                "startTimeLocal": "2026-10-09 08:00:00",
                "duration": 3600.5,
                "distance": 25000,
                "startLatitude": 55.7,
                "description": "private note",
            }
        )

        self.assertEqual(
            summary,
            {
                "garmin_activity_id": 42,
                "name": "Morning",
                "sport": "cycling",
                "start": "2026-10-09 08:00:00",
                "duration_sec": 3600.5,
                "distance_m": 25000.0,
            },
        )


class ActivitiesRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_does_not_require_a_secret(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_activities_reject_a_missing_secret(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/activities")
        self.assertEqual(response.status_code, 503)

    def test_activities_reject_a_bad_secret(self) -> None:
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = self.client.get("/activities", headers={"Authorization": "Bearer wrong"})
        self.assertEqual(response.status_code, 401)

    def test_activities_return_the_adapter_summary(self) -> None:
        summary = {
            "garmin_activity_id": 7,
            "name": "Ride",
            "sport": "cycling",
            "start": "2026-10-09 08:00:00",
            "duration_sec": 1000.0,
            "distance_m": 5000.0,
        }
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.fetch_recent_activities", return_value=[summary]):
                response = self.client.get(
                    "/activities?limit=1",
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"activities": [summary]})


if __name__ == "__main__":
    unittest.main()
