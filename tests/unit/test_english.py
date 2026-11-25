import unittest
from unittest.mock import patch

from app.ai.english import SYSTEM_PROMPT, EnglishError, review_english


def _answer():
    return {
        "verdict": "This is grammatical and sounds natural.",
        "revision": "My knee hurt after the run.",
        "alternatives": [
            {"tone": "casual", "text": "My knee hurt after the run."},
            {"tone": "polite", "text": "My knee was sore after the run."},
        ],
        "tweaks": [],
    }


class ReviewEnglishTest(unittest.TestCase):
    def test_empty_text_is_refused_before_any_call(self) -> None:
        with patch("app.ai.english.client.chat") as chat:
            with self.assertRaises(EnglishError) as caught:
                review_english("   ")
        self.assertEqual(caught.exception.reason, "empty")
        chat.assert_not_called()

    def test_a_sound_answer_is_kept(self) -> None:
        answer = _answer()
        with patch("app.ai.english.client.chat", return_value=answer) as chat:
            result = review_english("  My knee hurt after the run. ")
        sent = chat.call_args.args[0]
        self.assertEqual(sent[0]["role"], "system")
        self.assertEqual(sent[1]["content"], "My knee hurt after the run.")
        self.assertEqual(result, answer)

    def test_one_alternative_is_refused(self) -> None:
        answer = _answer()
        answer["alternatives"] = answer["alternatives"][:1]
        with patch("app.ai.english.client.chat", return_value=answer):
            with self.assertRaises(EnglishError) as caught:
                review_english("Fine.")
        self.assertEqual(caught.exception.reason, "bad_answer")

    def test_the_prompt_is_a_concise_adviser(self) -> None:
        self.assertIn("concise, friendly English language adviser", SYSTEM_PROMPT)
        self.assertIn("grammatically correct and sounds natural", SYSTEM_PROMPT)
        self.assertIn("preposition, spelling, or phrasing", SYSTEM_PROMPT)
        self.assertIn("casual and polite", SYSTEM_PROMPT)
        self.assertIn("British and American", SYSTEM_PROMPT)
        self.assertIn("programme", SYSTEM_PROMPT)
        self.assertIn("Do not add training advice", SYSTEM_PROMPT)
