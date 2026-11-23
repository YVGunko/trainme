"""Check the English in a note the athlete just typed.

This is a language exercise, not a training decision. The answer is not stored
and is not part of the coach context. The diary keeps the original words until
the athlete chooses to replace them.
"""

from __future__ import annotations

from typing import Any

from app.ai import client

_MAX_TEXT = 4000
_MAX_ASPECT = 80
_MAX_NOTE = 400

SYSTEM_PROMPT = """You help one athlete practice English while they write a training note.

Check the English of the text they send. Return one JSON object and nothing else:
no prose, no markdown, no code fence.

{"revision": "<a more correct English version of their text>",
 "tips": [{"aspect": "<short name of one language point>",
           "note": "<one sentence on what to notice>"}]}

Write the revision, the aspect, and the note in British English.
Prefer British spelling and vocabulary: programme, metre, favour, organised.
Do not use American spelling such as program, meter, or favorite when a British form exists.
Keep their meaning, names, numbers, and injuries.
Do not add training advice and do not invent facts they did not write.
Give two or three tips, never one and never more than three.
Each tip names one aspect, such as articles, tense, word order, prepositions, or word choice.
If the text is already sound, revision repeats it and the tips say what is already solid.
"""


class EnglishError(Exception):
    """Raised when the text or the model answer cannot be used."""

    def __init__(self, message: str, reason: str = "bad_text") -> None:
        super().__init__(message)
        self.reason = reason


def review_english(text: Any) -> dict[str, Any]:
    """Return a corrected British English version and two or three tips."""
    cleaned = _text(text)
    try:
        raw = client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": cleaned},
            ],
            {"required": ["revision", "tips"]},
        )
    except client.LlmNotConfigured as error:
        raise EnglishError("English check is not configured", "not_configured") from error
    except client.LlmRateLimited as error:
        raise EnglishError(str(error), "rate_limited") from error
    except client.LlmError as error:
        raise EnglishError("English check failed", "bad_answer") from error
    return _read(raw)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise EnglishError("Text must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise EnglishError("Text is empty", "empty")
    if len(cleaned) > _MAX_TEXT:
        raise EnglishError("Text is too long", "too_long")
    return cleaned


def _read(raw: dict[str, Any]) -> dict[str, Any]:
    revision = raw.get("revision")
    tips = raw.get("tips")
    if not isinstance(revision, str) or not revision.strip():
        raise EnglishError("Answer has no revision", "bad_answer")
    if not isinstance(tips, list) or not 2 <= len(tips) <= 3:
        raise EnglishError("Answer needs two or three tips", "bad_answer")
    clean = []
    for tip in tips:
        if not isinstance(tip, dict):
            raise EnglishError("A tip must be an object", "bad_answer")
        aspect = tip.get("aspect")
        note = tip.get("note")
        if not isinstance(aspect, str) or not aspect.strip() or len(aspect.strip()) > _MAX_ASPECT:
            raise EnglishError("A tip needs a short aspect", "bad_answer")
        if not isinstance(note, str) or not note.strip() or len(note.strip()) > _MAX_NOTE:
            raise EnglishError("A tip needs a short note", "bad_answer")
        clean.append({"aspect": aspect.strip(), "note": note.strip()})
    return {"revision": revision.strip(), "tips": clean}


__all__ = ["SYSTEM_PROMPT", "EnglishError", "review_english"]
