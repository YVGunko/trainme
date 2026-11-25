"""Check the English in a note the athlete just typed.

This is a language exercise, not a training decision. The answer is not stored
and is not part of the coach context. The diary keeps the original words until
the athlete chooses to replace them.
"""

from __future__ import annotations

from typing import Any

from app.ai import client

_MAX_TEXT = 4000
_MAX_VERDICT = 400
_MAX_TONE = 40
_MAX_ASPECT = 40
_MAX_NOTE = 400
_MAX_ALTERNATIVE = 4000

SYSTEM_PROMPT = """You are a concise, friendly English language adviser.

When the athlete sends a note, do three things:
1. Tell them whether it is grammatically correct and sounds natural.
2. Point out any small preposition, spelling, or phrasing tweaks.
3. Offer two or three natural alternatives, such as casual and polite, and note any British and American difference.

Return one JSON object and nothing else: no prose, no markdown, no code fence.

{"verdict": "<one short sentence>",
 "revision": "<the British version to put in their field>",
 "alternatives": [{"tone": "<casual|polite|british|american>",
                   "text": "<that way of saying it>"}],
 "tweaks": [{"aspect": "<preposition|spelling|phrasing|grammar>",
             "note": "<one short sentence>"}]}

revision is natural British English, the version they can drop into the field.
Prefer British spelling and vocabulary: programme, metre, favour, organised.
Do not use American spelling such as program, meter, or favorite when a British form exists.
Give two or three alternatives, never one and never more than three.
Each alternative has one tone: casual, polite, british, or american.
If British and American do not differ, do not invent a difference.
tweaks lists only real small changes. Use an empty list when there is nothing to tweak, and never more than three.
Keep their meaning, names, numbers, and injuries.
Do not add training advice and do not invent facts they did not write.
If the text is already sound, say so in the verdict and repeat it as revision.
"""


class EnglishError(Exception):
    """Raised when the text or the model answer cannot be used."""

    def __init__(self, message: str, reason: str = "bad_text") -> None:
        super().__init__(message)
        self.reason = reason


def review_english(text: Any) -> dict[str, Any]:
    """Return a verdict, a British revision, alternatives, and any small tweaks."""
    cleaned = _text(text)
    try:
        raw = client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": cleaned},
            ],
            {"required": ["verdict", "revision", "alternatives", "tweaks"]},
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
    verdict = _sentence(raw.get("verdict"), "verdict", _MAX_VERDICT)
    revision = _sentence(raw.get("revision"), "revision", _MAX_TEXT)
    alternatives = raw.get("alternatives")
    tweaks = raw.get("tweaks")
    if not isinstance(alternatives, list) or not 2 <= len(alternatives) <= 3:
        raise EnglishError("Answer needs two or three alternatives", "bad_answer")
    if not isinstance(tweaks, list) or len(tweaks) > 3:
        raise EnglishError("Answer has too many tweaks", "bad_answer")
    return {
        "verdict": verdict,
        "revision": revision,
        "alternatives": [_alternative(item) for item in alternatives],
        "tweaks": [_tweak(item) for item in tweaks],
    }


def _sentence(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise EnglishError(f"Answer needs a short {name}", "bad_answer")
    return value.strip()


def _alternative(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        raise EnglishError("An alternative must be an object", "bad_answer")
    tone = _sentence(item.get("tone"), "tone", _MAX_TONE).lower()
    text = _sentence(item.get("text"), "alternative", _MAX_ALTERNATIVE)
    return {"tone": tone, "text": text}


def _tweak(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        raise EnglishError("A tweak must be an object", "bad_answer")
    return {
        "aspect": _sentence(item.get("aspect"), "aspect", _MAX_ASPECT),
        "note": _sentence(item.get("note"), "tweak", _MAX_NOTE),
    }


__all__ = ["SYSTEM_PROMPT", "EnglishError", "review_english"]
