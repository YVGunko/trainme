"""Ask the coach for today's session and prove the answer is sendable.

The order matters and is the point of this module: the model writes a workout
description, and the description must pass the same ``build_workout`` check that
already guards a hand-written one. A model answer never reaches Garmin otherwise.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.ai import client
from app.ai.prompt import build_messages
from app.ai.schema import ANSWER_SCHEMA, AnswerShapeError, read_answer
from app.coach_context import build_context, coverage
from app.garmin.workout import WorkoutSpecError, build_workout


class RecommendationError(Exception):
    """Raised when an answer cannot be used.

    ``reason`` is a short code the web layer turns into a sentence.
    """

    def __init__(self, message: str, reason: str = "bad_answer") -> None:
        super().__init__(message)
        self.reason = reason


def recommend(today: date | None = None) -> dict[str, Any]:
    """Return a recommendation and its validated workout payload.

    Nothing is uploaded. The caller shows the result and decides.
    """
    context = build_context(today)
    answer = _ask(context)
    payload = _validated(answer["workout"])
    return {
        "recommendation": answer["recommendation"],
        "workout": answer["workout"],
        "garmin_payload": payload,
        "coverage": coverage(context),
    }


def _ask(context: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = client.chat(build_messages(context), ANSWER_SCHEMA)
    except client.LlmNotConfigured as error:
        raise RecommendationError("The coach has no API key", "not_configured") from error
    except client.LlmRateLimited as error:
        raise RecommendationError(str(error), "rate_limited") from error
    except client.LlmError as error:
        # The message already carries an excerpt of what the model said, which
        # is the only way to see why a schema-shaped answer was refused.
        raise RecommendationError(str(error), "bad_answer") from error
    try:
        return read_answer(raw)
    except AnswerShapeError as error:
        raise RecommendationError(str(error), "bad_answer") from error


def _validated(workout: dict[str, Any]) -> dict[str, Any]:
    """Run the workout description through the checks a Garmin upload uses."""
    try:
        return build_workout(workout)
    except WorkoutSpecError as error:
        # The model broke a rule the app enforces. The message is specific
        # enough to be worth showing, and nothing was uploaded.
        raise RecommendationError(str(error), "invalid_workout") from error


__all__ = ["RecommendationError", "recommend"]
