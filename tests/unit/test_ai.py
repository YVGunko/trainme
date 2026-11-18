import io
import json
import os
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from app.ai import client
from app.ai.prompt import SYSTEM_PROMPT, build_messages
from app.ai.recommend import RecommendationError, recommend
from app.ai.schema import ANSWER_SCHEMA, AnswerShapeError, read_answer

_WORKOUT = {
    "name": "Endurance",
    "sport": "cycling",
    "blocks": [
        {"steps": [{"kind": "warmup", "end": {"type": "time", "seconds": 600}}]},
    ],
}

_ANSWER = {
    "recommendation": {"summary": "Easy spin", "reason": "Load is high", "confidence": 0.7},
    "workout": _WORKOUT,
}


def _completion(content: dict | str) -> dict:
    text = content if isinstance(content, str) else json.dumps(content)
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


class ChatTest(unittest.TestCase):
    def test_a_missing_key_is_not_configured(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(client.LlmNotConfigured):
                client.chat([], ANSWER_SCHEMA)

    def test_is_configured_reflects_the_environment(self) -> None:
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            self.assertTrue(client.is_configured())
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(client.is_configured())

    def test_a_successful_call_returns_the_parsed_object(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(_completion(_ANSWER)).encode()
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: False
        with patch.dict(os.environ, {"LLM_API_KEY": "test-key-123"}, clear=True):
            with patch("urllib.request.urlopen", return_value=response) as open_url:
                result = client.chat([{"role": "user", "content": "x"}], ANSWER_SCHEMA)
        self.assertEqual(result["recommendation"]["summary"], "Easy spin")
        request = open_url.call_args.args[0]
        sent = json.loads(request.data.decode())
        self.assertEqual(sent["response_format"], {"type": "json_object"})
        self.assertFalse(sent["stream"])
        # The key travels in a header only, so it must be absent from the body.
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key-123")
        serialized = json.dumps(sent, sort_keys=True)
        self.assertNotIn("test-key-123", serialized)

    def test_the_model_defaults_to_deepseek(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(_completion(_ANSWER)).encode()
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: False
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            with patch("urllib.request.urlopen", return_value=response) as open_url:
                client.chat([], ANSWER_SCHEMA)
        self.assertEqual(open_url.call_args.args[0].full_url, "https://api.deepseek.com/chat/completions")

    def test_a_custom_base_url_is_honoured(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(_completion(_ANSWER)).encode()
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: False
        env = {"LLM_API_KEY": "k", "LLM_BASE_URL": "https://api.groq.com/openai/v1/"}
        with patch.dict(os.environ, env, clear=True):
            with patch("urllib.request.urlopen", return_value=response) as open_url:
                client.chat([], ANSWER_SCHEMA)
        self.assertEqual(
            open_url.call_args.args[0].full_url,
            "https://api.groq.com/openai/v1/chat/completions",
        )

    def test_a_429_is_a_rate_limit(self) -> None:
        error = urllib.error.HTTPError("u", 429, "slow", {}, io.BytesIO(b'{"error":{"message":"slow down"}}'))
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(client.LlmRateLimited):
                    client.chat([], ANSWER_SCHEMA)

    def test_an_empty_balance_is_a_rate_limit_not_a_crash(self) -> None:
        error = urllib.error.HTTPError("u", 402, "pay", {}, io.BytesIO(b'{"error":{"message":"no balance"}}'))
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=error):
                with self.assertRaises(client.LlmRateLimited):
                    client.chat([], ANSWER_SCHEMA)

    def test_a_connection_failure_names_the_cause_without_the_key(self) -> None:
        with patch.dict(os.environ, {"LLM_API_KEY": "secret-key"}, clear=True):
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
                with self.assertRaises(client.LlmError) as caught:
                    client.chat([], ANSWER_SCHEMA)
        self.assertNotIn("secret-key", str(caught.exception))

    def test_an_empty_answer_is_refused(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(_completion("")).encode()
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: False
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            with patch("urllib.request.urlopen", return_value=response):
                with self.assertRaises(client.LlmError):
                    client.chat([], ANSWER_SCHEMA)

    def test_answer_text_that_is_not_json_is_refused(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(_completion("sure! here is a plan")).encode()
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: False
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            with patch("urllib.request.urlopen", return_value=response):
                with self.assertRaises(client.LlmError):
                    client.chat([], ANSWER_SCHEMA)

    def test_a_missing_required_field_is_refused(self) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(_completion({"recommendation": {}})).encode()
        response.__enter__ = lambda self: response
        response.__exit__ = lambda *args: False
        with patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            with patch("urllib.request.urlopen", return_value=response):
                with self.assertRaises(client.LlmError):
                    client.chat([], ANSWER_SCHEMA)


class ReadAnswerTest(unittest.TestCase):
    def test_reads_a_well_formed_answer(self) -> None:
        answer = read_answer(_ANSWER)
        self.assertEqual(answer["recommendation"]["confidence"], 0.7)
        self.assertEqual(answer["workout"], _WORKOUT)

    def test_an_unknown_top_level_field_is_refused(self) -> None:
        with self.assertRaises(AnswerShapeError):
            read_answer({**_ANSWER, "garmin": {"workoutId": 1}})

    def test_confidence_must_be_a_number_between_zero_and_one(self) -> None:
        for value in ("high", True, 1.5, -0.1, None):
            with self.subTest(value=value):
                bad = {**_ANSWER, "recommendation": {**_ANSWER["recommendation"], "confidence": value}}
                with self.assertRaises(AnswerShapeError):
                    read_answer(bad)

    def test_blank_text_is_refused(self) -> None:
        for key in ("summary", "reason"):
            with self.subTest(key=key):
                bad = {**_ANSWER, "recommendation": {**_ANSWER["recommendation"], key: "  "}}
                with self.assertRaises(AnswerShapeError):
                    read_answer(bad)

    def test_a_missing_workout_is_refused(self) -> None:
        with self.assertRaises(AnswerShapeError):
            read_answer({"recommendation": _ANSWER["recommendation"]})


class SchemaTest(unittest.TestCase):
    def test_the_schema_covers_the_fields_the_validator_reads(self) -> None:
        from app.garmin.workout import _SPEC_KEYS

        properties = set(ANSWER_SCHEMA["properties"]["workout"]["properties"])
        # Every field the validator reads must be describable by the model, or
        # its answer would silently lose it.
        self.assertTrue(_SPEC_KEYS - {"duration_sec"} <= properties)

    def test_every_sport_the_builder_accepts_is_offered(self) -> None:
        from app.garmin.workout import _SPORTS

        self.assertEqual(set(ANSWER_SCHEMA["properties"]["workout"]["properties"]["sport"]["enum"]), set(_SPORTS))


class PromptTest(unittest.TestCase):
    def test_the_system_prompt_is_a_stable_prefix(self) -> None:
        first = build_messages({"today": "2026-11-18"})
        second = build_messages({"today": "2026-12-25"})
        # Prompt caching only pays off when the prefix is byte-identical.
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[0]["content"], SYSTEM_PROMPT)
        self.assertNotEqual(first[1], second[1])

    def test_athlete_data_goes_after_the_cacheable_part(self) -> None:
        messages = build_messages({"profile": {"notes": "hamstring"}})
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertIn("hamstring", messages[1]["content"])

    def test_the_prompt_names_the_data_artefacts(self) -> None:
        # A zero ACWR next to a small acute load is a Garmin gap, and reading it
        # as a fitness collapse would produce a wrong session.
        self.assertIn("acwr of 0", SYSTEM_PROMPT)
        self.assertIn("not a collapse", SYSTEM_PROMPT)

    def test_the_prompt_forbids_diagnosis_and_garmin_payloads(self) -> None:
        self.assertIn("Do not diagnose", SYSTEM_PROMPT)
        self.assertIn("Never describe Garmin API fields", SYSTEM_PROMPT)


class RecommendTest(unittest.TestCase):
    def test_a_good_answer_passes_the_existing_validator(self) -> None:
        with patch("app.ai.recommend.build_context", return_value={"today": "2026-11-18"}):
            with patch("app.ai.recommend.client.chat", return_value=_ANSWER):
                result = recommend()
        self.assertEqual(result["recommendation"]["summary"], "Easy spin")
        self.assertEqual(result["garmin_payload"]["sportType"]["sportTypeKey"], "cycling")
        self.assertEqual(len(result["garmin_payload"]["workoutSegments"][0]["workoutSteps"]), 1)

    def test_a_workout_the_validator_rejects_never_reaches_garmin(self) -> None:
        bad = {**_ANSWER, "workout": {**_WORKOUT, "sport": "swimming"}}
        with patch("app.ai.recommend.build_context", return_value={}):
            with patch("app.ai.recommend.client.chat", return_value=bad):
                with self.assertRaises(RecommendationError) as caught:
                    recommend()
        self.assertEqual(caught.exception.reason, "invalid_workout")

    def test_a_misspelled_field_is_a_shape_error(self) -> None:
        bad = {**_ANSWER, "recommendation": _ANSWER["recommendation"] | {"confidance": 0.5}}
        with patch("app.ai.recommend.build_context", return_value={}):
            with patch("app.ai.recommend.client.chat", return_value=bad):
                with self.assertRaises(RecommendationError):
                    recommend()

    def test_a_missing_key_says_so(self) -> None:
        with patch("app.ai.recommend.build_context", return_value={}):
            with patch("app.ai.recommend.client.chat", side_effect=client.LlmNotConfigured):
                with self.assertRaises(RecommendationError) as caught:
                    recommend()
        self.assertEqual(caught.exception.reason, "not_configured")

    def test_an_invented_exercise_is_refused_by_the_validator(self) -> None:
        bad_workout = {
            "name": "Strength",
            "sport": "strength_training",
            "blocks": [
                {
                    "steps": [
                        {
                            "kind": "interval",
                            "end": {"type": "reps", "count": 10},
                            "exercise": "Definitely Not An Exercise",
                        }
                    ]
                }
            ],
        }
        bad = {**_ANSWER, "workout": bad_workout}
        with patch("app.ai.recommend.build_context", return_value={}):
            with patch("app.ai.recommend.client.chat", return_value=bad):
                with self.assertRaises(RecommendationError) as caught:
                    recommend()
        self.assertEqual(caught.exception.reason, "invalid_workout")

    def test_coverage_travels_with_the_answer(self) -> None:
        with patch(
            "app.ai.recommend.build_context",
            return_value={"today": "2026-11-18", "recent_activities": [], "weekly_totals": []},
        ):
            with patch("app.ai.recommend.client.chat", return_value=_ANSWER):
                result = recommend()
        self.assertEqual(result["coverage"]["raw_activity_count"], 0)
