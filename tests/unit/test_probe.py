import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.garmin.probe import probe_unused
from app.main import app


class ProbeUnusedTest(unittest.TestCase):
    def test_reads_unused_methods_and_hides_secrets(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.get_activities_by_date.return_value = [
            {
                "activityId": 9,
                "activityName": "Run",
                "activityType": {"typeKey": "running"},
                "startTimeLocal": "2026-10-14 08:00:00",
                "access_token": "hidden",
            }
        ]
        client.get_activity_hr_in_timezones.return_value = [{"zoneNumber": 1, "secsInZone": 10}]
        client.get_hrv_data.return_value = {"hrvStatus": "BALANCED", "refresh_token": "hidden"}
        client.get_training_readiness.return_value = [{"score": 70}]
        client.get_daily_training_status.return_value = {"trainingStatusPhrase": "PRODUCTIVE"}
        client.get_max_metrics.return_value = {"vo2MaxValue": 48}
        client.get_training_four_week_load_balance.return_value = {"aerobicLow": 1}
        client.get_running_tolerance.return_value = [{"value": 2}]

        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key", "DATABASE_URL": "postgresql://local/trainme"}):
            with patch("app.garmin.probe.connect") as connect:
                connect.return_value.__enter__.return_value = MagicMock()
                with patch("app.garmin.probe.load_token", return_value="saved"):
                    with patch("app.garmin.probe._login", return_value=client):
                        with patch("app.garmin.probe.save_token") as save_token:
                            report = probe_unused(date(2026, 10, 14))

        save_token.assert_called_once()
        client.get_activities_by_date.assert_called_once_with("2026-10-14", "2026-10-14")
        client.get_activity_hr_in_timezones.assert_called_once_with("9")
        client.get_hrv_data.assert_called_once_with("2026-10-14")
        client.get_training_readiness.assert_called_once_with("2026-10-14")
        client.get_daily_training_status.assert_called_once_with("2026-10-14")
        client.get_max_metrics.assert_called_once_with("2026-10-14")
        client.get_training_four_week_load_balance.assert_called_once_with("2026-10-14")
        client.get_running_tolerance.assert_called_once_with("2026-10-14", "2026-10-14", "daily")
        self.assertEqual(report["activities"][0]["hr_time_in_zones"]["payload"][0]["secsInZone"], 10)
        self.assertEqual(report["activity_list"]["payload"][0]["access_token"], "<redacted>")
        self.assertEqual(report["daily"]["hrv"]["payload"]["refresh_token"], "<redacted>")
        self.assertEqual(report["daily"]["max_metrics"]["payload"]["vo2MaxValue"], 48)
        self.assertNotIn("hidden", str(report))

    def test_keeps_a_method_failure_in_the_report(self) -> None:
        client = MagicMock()
        client.client.dumps.return_value = "{}"
        client.profile_id = 7
        client.get_activities_by_date.return_value = []
        client.get_hrv_data.side_effect = RuntimeError("hrv down")

        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key", "DATABASE_URL": "postgresql://local/trainme"}):
            with patch("app.garmin.probe.connect") as connect:
                connect.return_value.__enter__.return_value = MagicMock()
                with patch("app.garmin.probe.load_token", return_value="saved"):
                    with patch("app.garmin.probe._login", return_value=client):
                        with patch("app.garmin.probe.save_token"):
                            report = probe_unused(date(2026, 10, 14))

        self.assertEqual(report["activities"], [])
        self.assertEqual(report["daily"]["hrv"]["ok"], False)
        self.assertEqual(report["daily"]["hrv"]["error"], "RuntimeError")
        self.assertTrue(report["daily"]["training_readiness"]["ok"])


class ProbeRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/probe/unused-garmin", json={"date": "2026-10-14"})
        self.assertEqual(response.status_code, 401)

    def test_rejects_a_bad_date(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/probe/unused-garmin",
                json={"date": "today"},
                headers={"Authorization": "Bearer expected"},
            )
        self.assertEqual(response.status_code, 400)

    def test_returns_the_report(self) -> None:
        client = TestClient(app)
        report = {"date": "2026-10-14", "activities": [], "daily": {}}
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.probe_unused", return_value=report):
                response = client.post(
                    "/probe/unused-garmin",
                    json={"date": "2026-10-14"},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), report)
        self.assertNotIn("di_token", response.text)
