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
    load_active_recommendation,
    replace_recommendation,
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


def recommend(
    today: date | None = None,
    regenerate: bool = False,
    adjust: bool = True,
) -> dict[str, Any]:
    """Return the plan in force, possibly adjusted, or a new one.

    A plan covers a stretch of days, so it stays in force until its last day has
    passed. Each call then does one of three things:

    - returns the stored plan unchanged, when it does not need touching;
    - asks the model to adjust the remaining days, keeping the part of the week
      that still fits what the athlete has actually done;
    - builds a new week, when the old one has run out or ``regenerate`` is set.

    ``adjust=False`` returns the stored plan as it is, for a plain read.
    """
    now = today or date.today()
    day = now.isoformat()
    stored = _active(day)

    if stored is not None and not regenerate:
        if not adjust:
            return stored | {"stored": True, "adjusted": False}
        result, changed = _adjust(now, stored)
        return result | {"stored": True, "adjusted": changed}

    return _fresh(now) | {"stored": False, "adjusted": False}


def _fresh(now: date) -> dict[str, Any]:
    """Build a week from scratch and store it."""
    context = build_context(now)
    answer = _ask(build_messages(context))
    days, unmatched = _with_catalog_names(answer["days"])
    payloads = _validated(days)
    result: dict[str, Any] = {
        "recommendation": answer["recommendation"],
        "days": days,
        "garmin_payloads": payloads,
        "coverage": coverage(context),
    }
    if unmatched:
        result["unmatched_exercises"] = unmatched
    _remember(now.isoformat(), result, replace=True)
    return result


def _adjust(now: date, stored: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Ask the model to revise the remaining days of a stored plan.

    Days that have already passed are dropped rather than revised: the athlete
    cannot train them. What remains is sent back with the current data, so the
    model can keep what still fits and change what does not.
    """
    remaining = _remaining(stored, now)
    if not remaining:
        return _fresh(now), True

    context = build_context(now)
    context["existing_plan"] = remaining
    try:
        answer = _ask(build_messages(context))
    except RecommendationError as error:
        # The stored plan is still usable. Losing it because a revision failed
        # would leave the athlete with nothing, so the old plan is returned.
        logger.warning("Plan adjustment failed: %s", error.reason)
        return stored | {"days": remaining}, False

    days, unmatched = _with_catalog_names(answer["days"])
    payloads = _validated(days)
    result: dict[str, Any] = {
        "recommendation": answer["recommendation"],
        "days": days,
        "garmin_payloads": payloads,
        "coverage": coverage(context),
    }
    if unmatched:
        result["unmatched_exercises"] = unmatched
    _remember(stored.get("built_on") or now.isoformat(), result, replace=True)
    return result, True


def _remaining(stored: dict[str, Any], now: date) -> list[dict[str, Any]]:
    day = now.isoformat()
    return [
        entry
        for entry in stored.get("days") or []
        if isinstance(entry, dict) and str(entry.get("date", "")) >= day
    ]


def _active(day: str) -> dict[str, Any] | None:
    with connect() as connection:
        ensure_schema(connection)
        return load_active_recommendation(connection, day)


def _remember(day: str, result: dict[str, Any], replace: bool) -> None:
    try:
        with connect() as connection:
            if replace:
                replace_recommendation(connection, day, result)
            else:
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
