import unittest
from unittest.mock import patch

from app.ai.english import SYSTEM_PROMPT, EnglishError, review_english


class ReviewEnglishTest(unittest.TestCase):
    def test_empty_text_is_refused_before_any_call(self) -> None:
        with patch("app.ai.english.client.chat") as chat:
            with self.assertRaises(EnglishError) as caught:
                review_english("   ")
        self.assertEqual(caught.exception.reason, "empty")
        chat.assert_not_called()

    def test_a_sound_answer_is_kept(self) -> None:
        answer = {
            "revision": "My knee hurt after the run.",
            "tips": [
                {"aspect": "Время", "note": "Hurt уже в прошедшем, это верно."},
                {"aspect": "Артикль", "note": "The run уместен: речь о конкретной пробежке."},
            ],
        }
        with patch("app.ai.english.client.chat", return_value=answer) as chat:
            result = review_english("  My knee hurt after the run. ")
        sent = chat.call_args.args[0]
        self.assertEqual(sent[0]["role"], "system")
        self.assertEqual(sent[1]["content"], "My knee hurt after the run.")
        self.assertEqual(result, answer)

    def test_one_tip_is_refused(self) -> None:
        answer = {
            "revision": "Fine.",
            "tips": [{"aspect": "Порядок слов", "note": "Порядок уже верный."}],
        }
        with patch("app.ai.english.client.chat", return_value=answer):
            with self.assertRaises(EnglishError) as caught:
                review_english("Fine.")
        self.assertEqual(caught.exception.reason, "bad_answer")

    def test_the_prompt_keeps_the_lesson_in_russian_and_the_text_in_english(self) -> None:
        self.assertIn("Write revision in English", SYSTEM_PROMPT)
        self.assertIn("Write aspect and note in Russian", SYSTEM_PROMPT)
        self.assertIn("Do not add training advice", SYSTEM_PROMPT)
