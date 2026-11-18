import json
import os
import unittest
from unittest.mock import MagicMock, patch

from app.ai import client, exercise_resolve
from app.ai.exercise_match import match_exercise
from app.ai.exercise_resolve import ResolutionError, resolve


def _completion(content: dict) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(
        {"choices": [{"message": {"role": "assistant", "content": json.dumps(content)}}]}
    ).encode()
    response.__enter__ = lambda self: response
    response.__exit__ = lambda *args: False
    return response


class QuestionTest(unittest.TestCase):
    def test_nothing_to_resolve_makes_no_call(self) -> None:
        with patch("app.ai.exercise_resolve.client.chat") as chat:
            self.assertEqual(resolve([]), {})
        chat.assert_not_called()

    def test_the_question_carries_candidates_only_for_ambiguous_names(self) -> None:
        ambiguous = match_exercise("Glute Bridge")
        missing = match_exercise("Nordic Hamstring Curl")
        payload = exercise_resolve._question([ambiguous, missing])
        by_query = {item["movement"]: item["candidates"] for item in payload}
        self.assertTrue(by_query["Glute Bridge"])
        self.assertEqual(by_query["Nordic Hamstring Curl"], [])

    def test_the_question_does_not_carry_the_training_context(self) -> None:
        # The second call must stay narrow; re-sending the athlete's data would
        # cost as much as the first and leak it twice.
        payload = exercise_resolve._question([match_exercise("Glute Bridge")])
        text = json.dumps(payload)
        for field in ("profile", "recent_days", "weekly_totals", "wellness"):
            self.assertNotIn(field, text)


class ResolveTest(unittest.TestCase):
    def _resolve(self, answer: dict, queries=("Glute Bridge",)) -> dict:
        unresolved = [match_exercise(q) for q in queries]
        env = {"LLM_API_KEY": "k"}
        with patch.dict(os.environ, env, clear=True):
            with patch("urllib.request.urlopen", return_value=_completion(answer)):
                return resolve(unresolved)

    def test_a_chosen_candidate_is_returned(self) -> None:
        found = self._resolve(
            {"choices": [{"query": "Glute Bridge", "match": "Banded Glute Bridge"}]}
        )
        self.assertEqual(found["Glute Bridge"], "Banded Glute Bridge")

    def test_a_name_outside_the_offered_list_is_refused(self) -> None:
        # Accepting an unoffered name would let the model reintroduce exactly the
        # invented-name problem the matcher exists to prevent.
        found = self._resolve(
            {"choices": [{"query": "Glute Bridge", "match": "Weighted Glute Bridge"}]}
        )
        self.assertIsNone(found["Glute Bridge"])

    def test_null_means_the_catalog_has_nothing_for_it(self) -> None:
        found = self._resolve(
            {"choices": [{"query": "Nordic Hamstring Curl", "match": None}]},
            queries=("Nordic Hamstring Curl",),
        )
        self.assertIsNone(found["Nordic Hamstring Curl"])

    def test_a_movement_left_out_of_the_answer_stays_unresolved(self) -> None:
        found = self._resolve({"choices": []})
        self.assertIsNone(found["Glute Bridge"])

    def test_an_answer_about_an_unasked_movement_is_ignored(self) -> None:
        found = self._resolve(
            {"choices": [{"query": "Something Else", "match": "Banded Glute Bridge"}]}
        )
        self.assertIsNone(found["Glute Bridge"])

    def test_every_queried_movement_gets_an_entry(self) -> None:
        found = self._resolve(
            {"choices": [{"query": "Glute Bridge", "match": "Banded Glute Bridge"}]},
            queries=("Glute Bridge", "Nordic Hamstring Curl"),
        )
        self.assertEqual(set(found), {"Glute Bridge", "Nordic Hamstring Curl"})
        self.assertIsNone(found["Nordic Hamstring Curl"])

    def test_a_missing_choices_field_is_an_error(self) -> None:
        with self.assertRaises(ResolutionError):
            self._resolve({"something": []})

    def test_a_provider_failure_is_reported(self) -> None:
        unresolved = [match_exercise("Glute Bridge")]
        with patch(
            "app.ai.exercise_resolve.client.chat",
            side_effect=client.LlmRateLimited("slow", 429),
        ):
            with self.assertRaises(ResolutionError):
                resolve(unresolved)


if __name__ == "__main__":
    unittest.main()
