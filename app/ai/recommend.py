"""Ask the coach for today's session and prove the answer is sendable.

The order matters and is the point of this module: the model writes a workout
description, exercise names are matched against the real catalog, and the result
must pass the same ``build_workout`` check that guards a hand-written workout. A
model answer never reaches Garmin otherwise.

An exercise the catalog cannot name is not silently replaced. A step is either
sent with a name the catalog holds, or left out of the workout and reported, so
the athlete can add it by hand.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.ai import client, exercise_resolve
from app.ai.exercise_match import match_exercise
from app.ai.prompt import build_messages
from app.ai.schema import ANSWER_SCHEMA, AnswerShapeError, read_answer
from app.coach_context import build_context, coverage
from app.garmin.workout import WorkoutSpecError, build_workout


class RecommendationError(Exception):
    """Raised when an answer cannot be used.

    ``reason`` is a short code the web layer turns into a sentence.
    ``partial`` carries what was already learned, so a refusal is still useful.
    """

    def __init__(
        self,
        message: str,
        reason: str = "bad_answer",
        partial: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.partial = partial or {}


def recommend(today: date | None = None) -> dict[str, Any]:
    """Return a recommendation and its validated workout payload.

    Nothing is uploaded. The caller shows the result and decides.
    """
    context = build_context(today)
    answer = _ask(context)
    workout, unmatched = _with_catalog_names(answer["workout"])
    payload = _validated(workout)
    result: dict[str, Any] = {
        "recommendation": answer["recommendation"],
        "workout": workout,
        "garmin_payload": payload,
        "coverage": coverage(context),
    }
    if unmatched:
        # Reported rather than dropped quietly: the athlete should know a
        # prescribed movement is not on the watch.
        result["unmatched_exercises"] = unmatched
    return result


def _with_catalog_names(workout: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Replace plain-language exercise names with catalog names.

    Returns the workout and the movements the catalog could not name. A step
    whose exercise cannot be named is removed, because a rep step without an
    exercise cannot be built, and sending a different movement would misrepresent
    the plan.
    """
    _mapping_shape(workout)
    renamed: list[tuple[str, str]] = []
    unmatched: list[str] = []
    for block in workout.get("blocks") or []:
        for step in block.get("steps") or []:
            name = step.get("exercise")
            if not isinstance(name, str) or not name.strip():
                continue
            match = match_exercise(name)
            if match.settled:
                step["exercise"] = match.entry["name"]
                renamed.append((name, match.entry["name"]))
                continue
            step["exercise"] = name
            unmatched.append(name)

    if renamed or unmatched:
        resolved = _resolve_unmatched(workout, unmatched)
        unmatched = [name for name in unmatched if name not in resolved]
        _drop_unmatched_steps(workout, unmatched)
    return workout, unmatched


def _resolve_unmatched(workout: dict[str, Any], unmatched: list[str]) -> dict[str, str]:
    """Ask the narrow second question and apply the answers to the steps."""
    if not unmatched:
        return {}
    matches = [match_exercise(name) for name in unmatched]
    try:
        chosen = exercise_resolve.resolve(matches)
    except exercise_resolve.ResolutionError:
        # The first answer is already a usable plan. Losing it because a narrow
        # follow-up failed would be worse than omitting the steps it was asked
        # about, so they are dropped and reported instead.
        return {}
    resolved = {name: picked for name, picked in chosen.items() if picked}
    for block in workout.get("blocks") or []:
        for step in block.get("steps") or []:
            name = step.get("exercise")
            if isinstance(name, str) and name in resolved:
                step["exercise"] = resolved[name]
    return resolved


def _drop_unmatched_steps(workout: dict[str, Any], unmatched: list[str]) -> None:
    """Remove steps whose exercise the catalog cannot name."""
    keep: list[dict[str, Any]] = []
    for block in workout.get("blocks") or []:
        steps = [
            step
            for step in (block.get("steps") or [])
            if not (
                isinstance(step.get("exercise"), str) and step["exercise"] in unmatched
            )
        ]
        if steps:
            block["steps"] = steps
            keep.append(block)
    workout["blocks"] = keep


def _mapping_shape(workout: dict[str, Any]) -> None:
    if not isinstance(workout.get("blocks"), list):
        raise RecommendationError("Workout has no blocks", "invalid_workout")


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
