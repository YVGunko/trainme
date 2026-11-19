"""The shape a coach answer must have.

The schema is deliberately narrow: it is the workout description the validator
already accepts, plus a recommendation and its reason. Anything the model adds
is ignored, and anything required that is missing is refused before validation
runs, so a bad answer never reaches Garmin.

Kept as plain JSON rather than a pydantic model because it is sent to the
provider as a schema and checked here by hand: two sources of truth for one
shape is how they drift apart.
"""

from __future__ import annotations

from typing import Any

SPORTS = ("running", "cycling", "strength_training", "yoga", "mobility")

# The workout object mirrors app.garmin.workout._SPEC_KEYS. A field added there
# without being added here would be dropped, so the test suite compares them.
ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recommendation", "days"],
    "properties": {
        "recommendation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "reason", "confidence"],
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One sentence: the shape of the week ahead.",
                },
                "reason": {
                    "type": "string",
                    "description": "Why, referring to the athlete's own data.",
                },
                "confidence": {
                    "type": "number",
                    "description": "0 to 1. Low when the data is thin or conflicting.",
                },
            },
        },
        "days": {
            "type": "array",
            "description": "One entry per day of the plan, oldest first.",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["date", "kind"],
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD."},
                    "kind": {
                        "type": "string",
                        "enum": ["workout", "rest"],
                        "description": "rest means no session that day.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional: why this day is shaped this way.",
                    },
                    "workouts": {
                        "type": "array",
                        "description": (
                            "Sessions for that day. A day can hold more than one, "
                            "such as a strength session and a ride. Empty on a rest day."
                        ),
                        "minItems": 1,
                        "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "sport", "blocks"],
                        "properties": {
                            "name": {"type": "string"},
                            "sport": {"type": "string", "enum": list(SPORTS)},
                            "description": {"type": "string"},
                            "blocks": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["steps"],
                                    "properties": {
                                        "repeat": {"type": "integer", "minimum": 1},
                                        "steps": {
                                            "type": "array",
                                            "minItems": 1,
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": ["kind", "end"],
                                                "properties": {
                                                    "kind": {
                                                        "type": "string",
                                                        "enum": [
                                                            "warmup",
                                                            "interval",
                                                            "recovery",
                                                            "cooldown",
                                                            "rest",
                                                        ],
                                                    },
                                                    "end": {
                                                        "type": "object",
                                                        "additionalProperties": False,
                                                        "required": ["type"],
                                                        "properties": {
                                                            "type": {
                                                                "type": "string",
                                                                "enum": ["time", "distance", "reps"],
                                                            },
                                                            "seconds": {"type": "number"},
                                                            "meters": {"type": "number"},
                                                            "count": {"type": "integer"},
                                                        },
                                                    },
                                                    "exercise": {
                                                        "type": "string",
                                                        "description": "Catalog name, strength, yoga, and mobility only.",
                                                    },
                                                    "weight_kg": {"type": "number"},
                                                    "target": {"type": "object"},
                                                    "secondary_target": {"type": "object"},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        },
                    },
                },
            },
        },
    },
}


class AnswerShapeError(Exception):
    """Raised when an answer does not match the schema."""


def read_answer(payload: Any) -> dict[str, Any]:
    """Return the recommendation and the planned days, or refuse with the field at fault."""
    if not isinstance(payload, dict):
        raise AnswerShapeError("Answer is not an object")
    unknown = sorted(set(payload) - {"recommendation", "days"})
    if unknown:
        raise AnswerShapeError(f"Answer has an unknown field: {unknown[0]}")

    recommendation = payload.get("recommendation")
    if not isinstance(recommendation, dict):
        raise AnswerShapeError("Answer has no recommendation")
    extra = sorted(set(recommendation) - {"summary", "reason", "confidence"})
    if extra:
        # A misspelled field would otherwise pass silently and the real value
        # would be missing, so the shape check has to be strict here too.
        raise AnswerShapeError(f"recommendation has an unknown field: {extra[0]}")
    summary = _text(recommendation, "summary")
    reason = _text(recommendation, "reason")
    confidence = recommendation.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise AnswerShapeError("recommendation.confidence must be a number")
    if not 0 <= float(confidence) <= 1:
        raise AnswerShapeError("recommendation.confidence must be between 0 and 1")

    days = payload.get("days")
    if not isinstance(days, list) or not days:
        raise AnswerShapeError("Answer has no days")
    return {
        "recommendation": {
            "summary": summary,
            "reason": reason,
            "confidence": float(confidence),
        },
        # Each workout goes to the existing validator untouched: this layer only
        # checks the object is present and shaped, not that a step makes sense
        # for the sport.
        "days": [_day(index, entry) for index, entry in enumerate(days)],
    }


def _day(index: int, entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise AnswerShapeError(f"days[{index}] is not an object")
    extra = sorted(set(entry) - {"date", "kind", "reason", "workouts"})
    if extra:
        raise AnswerShapeError(f"days[{index}] has an unknown field: {extra[0]}")
    day = entry.get("date")
    if not isinstance(day, str) or len(day) != 10:
        raise AnswerShapeError(f"days[{index}].date must be YYYY-MM-DD")
    kind = entry.get("kind")
    if kind not in {"workout", "rest"}:
        raise AnswerShapeError(f"days[{index}].kind must be workout or rest")

    workouts = entry.get("workouts")
    if kind == "rest":
        if workouts:
            raise AnswerShapeError(f"days[{index}] is a rest day and cannot carry a workout")
        result: dict[str, Any] = {"date": day, "kind": "rest"}
    else:
        # A day may hold more than one session, such as a lift and a ride.
        if not isinstance(workouts, list) or not workouts:
            raise AnswerShapeError(f"days[{index}] is a workout day with no workouts")
        for position, workout in enumerate(workouts):
            if not isinstance(workout, dict):
                raise AnswerShapeError(f"days[{index}].workouts[{position}] is not an object")
        result = {"date": day, "kind": "workout", "workouts": workouts}

    reason = entry.get("reason")
    if isinstance(reason, str) and reason.strip():
        result["reason"] = reason.strip()
    return result


def _text(value: dict[str, Any], key: str) -> str:
    found = value.get(key)
    if not isinstance(found, str) or not found.strip():
        raise AnswerShapeError(f"recommendation.{key} must be text")
    return found.strip()


__all__ = ["ANSWER_SCHEMA", "AnswerShapeError", "SPORTS", "read_answer"]
