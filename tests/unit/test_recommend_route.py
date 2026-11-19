import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ai.client import LlmNotConfigured
from app.ai.recommend import RecommendationError
from app.main import app

_SUMMARY = {
    "recommendation": {"summary": "Easy spin", "reason": "Load is high", "confidence": 0.7},
    "workout": {"name": "Endurance", "sport": "cycling", "blocks": []},
    "garmin_payload": {"sportType": {"sportTypeKey": "cycling"}},
    "coverage": {"raw_activity_count": 0},
}


class RecommendRouteTest(unittest.TestCase):
    def test_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            self.assertEqual(client.post("/recommend", json={}).status_code, 401)

    def test_returns_the_recommendation(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.recommend", return_value=_SUMMARY) as run:
                response = client.post(
                    "/recommend", json={}, headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), _SUMMARY)
        self.assertIsNone(run.call_args.args[0])

    def test_a_given_day_is_parsed(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.recommend", return_value=_SUMMARY) as run:
                client.post(
                    "/recommend",
                    json={"date": "2026-11-18"},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(run.call_args.args[0].isoformat(), "2026-11-18")

    def test_a_bad_date_is_a_bad_request(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/recommend",
                json={"date": "18.11.2026"},
                headers={"Authorization": "Bearer expected"},
            )
        self.assertEqual(response.status_code, 400)

    def test_no_key_is_unconfigured_not_a_failure(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch(
                "app.main.recommend",
                side_effect=RecommendationError("no key", "not_configured"),
            ):
                response = client.post(
                    "/recommend", json={}, headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 503)

    def test_a_rate_limit_is_a_rate_limit(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch(
                "app.main.recommend",
                side_effect=RecommendationError("slow down", "rate_limited"),
            ):
                response = client.post(
                    "/recommend", json={}, headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 429)

    def test_a_refused_answer_carries_its_reason(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch(
                "app.main.recommend",
                side_effect=RecommendationError("Sport must be running", "invalid_workout"),
            ):
                response = client.post(
                    "/recommend", json={}, headers={"Authorization": "Bearer expected"}
                )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["reason"], "invalid_workout")

    def test_a_read_does_not_ask_the_coach_for_a_revision(self) -> None:
        # Opening the plan page must not cost a model call.
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.recommend", return_value=_SUMMARY) as run:
                client.post(
                    "/recommend",
                    json={"adjust": False},
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertIs(run.call_args.kwargs["adjust"], False)

    def test_adjust_defaults_to_true(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.recommend", return_value=_SUMMARY) as run:
                client.post("/recommend", json={}, headers={"Authorization": "Bearer expected"})
        self.assertIs(run.call_args.kwargs["adjust"], True)

    def test_a_non_boolean_adjust_is_refused(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post(
                "/recommend",
                json={"adjust": "no"},
                headers={"Authorization": "Bearer expected"},
            )
        self.assertEqual(response.status_code, 400)

    def test_the_key_never_appears_in_the_response(self) -> None:
        client = TestClient(app)
        env = {"SERVICE_SECRET": "expected", "LLM_API_KEY": "sk-secret-value"}
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "app.main.recommend",
                side_effect=LlmNotConfigured,
            ):
                response = client.post(
                    "/recommend", json={}, headers={"Authorization": "Bearer expected"}
                )
        self.assertNotIn("sk-secret-value", response.text)


if __name__ == "__main__":
    unittest.main()
