import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from garminconnect import (
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from app.main import app
from app.storage.db import load_days


class RefreshDaysRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            self.assertEqual(client.post("/maintenance/refresh-days").status_code, 401)

    def test_returns_the_refresh_summary(self) -> None:
        client = TestClient(app)
        summary = {
            "day_count": 2,
            "refreshed_count": 2,
            "failed": [],
            "days": [
                {"day": "2026-11-17", "sleep_downloaded": False},
                {"day": "2026-11-18", "sleep_downloaded": False},
            ],
        }
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.refresh_stored_days", return_value=summary) as run:
                response = client.post(
                    "/maintenance/refresh-days", headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)
        run.assert_called_once_with()

    def test_a_rate_limit_is_reported_as_a_rate_limit(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch(
                "app.main.refresh_stored_days",
                side_effect=GarminConnectTooManyRequestsError("slow down"),
            ):
                response = client.post(
                    "/maintenance/refresh-days", headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 429)

    def test_a_garmin_failure_is_a_bad_gateway(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch(
                "app.main.refresh_stored_days",
                side_effect=GarminConnectConnectionError("down"),
            ):
                response = client.post(
                    "/maintenance/refresh-days", headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 502)

    def test_an_unconfigured_service_is_not_a_failure(self) -> None:
        from app.storage.crypto import EncryptionKeyMissing

        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.refresh_stored_days", side_effect=EncryptionKeyMissing()):
                response = client.post(
                    "/maintenance/refresh-days", headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 503)


class ReadDaysRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            self.assertEqual(client.get("/days").status_code, 401)

    def test_returns_the_days_with_their_hrv(self) -> None:
        client = TestClient(app)
        rows = [{"date": "2026-11-18", "overnight_hrv": 62.0}]
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.connect"), patch("app.main.ensure_schema"):
                with patch("app.main.load_days", return_value=rows):
                    response = client.get("/days", headers={"Authorization": "Bearer expected"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"days": rows})

    def test_a_bad_limit_is_rejected(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            for value in ("0", "91", "abc"):
                with self.subTest(value=value):
                    response = client.get(
                        f"/days?limit={value}", headers={"Authorization": "Bearer expected"}
                    )
                    self.assertEqual(response.status_code, 422)


class LoadDaysTest(unittest.TestCase):
    def test_returns_newest_last(self) -> None:
        connection = MagicMock()
        # The query takes the newest rows first so LIMIT keeps them, then the
        # reader reverses the list to read as a timeline.
        connection.execute.return_value.fetchall.return_value = [
            ("2026-11-18", 48.0, 62.0, "BALANCED", None, None, None, None, None, None, None, None),
            ("2026-11-17", 47.0, 61.0, "BALANCED", None, None, None, None, None, None, None, None),
        ]
        rows = load_days(connection, 30)
        self.assertEqual([row["date"] for row in rows], ["2026-11-17", "2026-11-18"])
        self.assertEqual(rows[1]["overnight_hrv"], 62.0)

    def test_the_query_selects_the_hrv_column(self) -> None:
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        load_days(connection, 30)
        sql = " ".join(connection.execute.call_args.args[0].split()).lower()
        self.assertIn("overnight_hrv", sql)
        self.assertIn("order by date desc", sql)
