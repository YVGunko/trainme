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

import logging
from datetime import date
from typing import Any

from app.ai import client, exercise_resolve
from app.ai.exercise_match import match_exercise
from app.ai.prompt import build_messages
from app.ai.schema import ANSWER_SCHEMA, AnswerShapeError, read_answer
from app.coach_context import build_context, coverage
from app.garmin.workout import WorkoutSpecError, build_workout
from app.storage.db import (
    connect,
    ensure_schema,
    load_recommendation,
    save_recommendation,
)

logger = logging.getLogger(__name__)


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


def recommend(today: date | None = None, regenerate: bool = False) -> dict[str, Any]:
    """Return a week plan, with every workout validated and ready to send.

    One plan is kept per day, so the 11:00 and 23:00 runs agree. ``regenerate``
    asks for a new plan and replaces the stored one; the athlete is the only
    caller that should set it, because two different plans in one day cannot be
    told apart from an unstable one.

    Nothing is uploaded. The caller shows the plan and decides which days to send.
    """
    day = (today or date.today()).isoformat()
    if not regenerate:
        stored = _stored(day)
        if stored is not None:
            return stored | {"stored": True}

    context = build_context(today)
    answer = _ask(context)
    days, unmatched = _with_catalog_names(answer["days"])
    payloads = _validated(days)
    result: dict[str, Any] = {
        "recommendation": answer["recommendation"],
        "days": days,
        "garmin_payloads": payloads,
        "coverage": coverage(context),
    }
    if unmatched:
        # Reported rather than dropped quietly: the athlete should know a
        # prescribed movement is not on the watch.
        result["unmatched_exercises"] = unmatched
    _remember(day, result)
    return result | {"stored": False}


def _stored(day: str) -> dict[str, Any] | None:
    with connect() as connection:
        ensure_schema(connection)
        return load_recommendation(connection, day)


def _remember(day: str, result: dict[str, Any]) -> None:
    try:
        with connect() as connection:
            save_recommendation(connection, day, result)
    except Exception as error:
        # The answer is already in hand. Losing the stored copy would only mean
        # the next run asks again, so it must not fail the response.
        logger.warning("Recommendation not stored: %s", type(error).__name__)


def _with_catalog_names(
    days: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Replace plain-language exercise names with catalog names, across the week.

    Every workout in the plan is scanned first, then the names the catalog could
    not settle are asked about in one narrow question, so a week costs one
    follow-up rather than one per day.

    A step whose exercise cannot be named is removed: a rep step without an
    exercise cannot be built, and sending a different movement would misrepresent
    the plan.
    """
    unmatched: list[str] = []
    for day in days:
        for workout in day.get("workouts") or []:
            if not isinstance(workout, dict):
                continue
            _mapping_shape(workout)
            for step in _steps(workout):
                name = step.get("exercise")
                if not isinstance(name, str) or not name.strip():
                    continue
                match = match_exercise(name)
                if match.settled:
                    step["exercise"] = match.entry["name"]
                else:
                    unmatched.append(name)

    if unmatched:
        resolved = _resolve_unmatched(days, unmatched)
        unmatched = [name for name in unmatched if name not in resolved]
        for day in days:
            for workout in day.get("workouts") or []:
                if isinstance(workout, dict):
                    _drop_unmatched_steps(workout, unmatched)
    return days, unmatched


def _steps(workout: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for block in workout.get("blocks") or []:
        for step in block.get("steps") or []:
            if isinstance(step, dict):
                found.append(step)
    return found


def _resolve_unmatched(
    days: list[dict[str, Any]], unmatched: list[str]
) -> dict[str, str]:
    """Ask the narrow second question and apply the answers across the week."""
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
    for day in days:
        for workout in day.get("workouts") or []:
            if not isinstance(workout, dict):
                continue
            for step in _steps(workout):
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


def _validated(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run every session in the plan through the checks a Garmin upload uses.

    A day may hold several sessions, so each one gets its own payload and its
    own date. One bad session refuses the whole plan: a week the athlete cannot
    act on is not better for being partly valid, and the message names the day.
    """
    payloads: list[dict[str, Any]] = []
    for day in days:
        for workout in day.get("workouts") or []:
            if not isinstance(workout, dict):
                continue
            try:
                payloads.append(
                    {"date": day["date"], "garmin_payload": build_workout(workout)}
                )
            except WorkoutSpecError as error:
                # The model broke a rule the app enforces. Naming the day makes
                # the refusal actionable, and nothing was uploaded.
                raise RecommendationError(
                    f"{day['date']}: {error}", "invalid_workout"
                ) from error
    return payloads


__all__ = ["RecommendationError", "recommend"]
