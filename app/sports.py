"""Fold Garmin's activity type names into the sports this app can programme.

Garmin reports well over a hundred type keys ("road_biking", "indoor_cycling",
"stand_up_paddleboarding_v2"), while a workout can only be built for five. The
model should never have to guess which of Garmin's names maps to which of ours,
so the folding happens here, once, on the way in.

A sport this app cannot programme is kept out of the workout decision but is not
thrown away: it still counts as training the athlete did, so it folds to a
recognised bucket and keeps its own name alongside for the model to read.
"""

from __future__ import annotations

from typing import Any

# The sports a workout can be built for. Order is the order the schema lists.
SPORTS = ("running", "cycling", "strength_training", "yoga", "mobility")

# Everything Garmin can report, folded into the five. A key not here is
# "other": real training that this app cannot programme.
_BY_TYPE_KEY = {
    # cycling family
    "cycling": "cycling",
    "road_biking": "cycling",
    "indoor_cycling": "cycling",
    "mountain_biking": "cycling",
    "gravel_cycling": "cycling",
    "cyclocross": "cycling",
    "track_cycling": "cycling",
    "downhill_biking": "cycling",
    "recumbent_cycling": "cycling",
    "virtual_ride": "cycling",
    "e_bike_fitness": "cycling",
    "e_bike_mountain": "cycling",
    "commuting": "cycling",
    "bmx": "cycling",
    # running family
    "running": "running",
    "indoor_running": "running",
    "trail_running": "running",
    "treadmill_running": "running",
    "track_running": "running",
    "virtual_run": "running",
    "ultra_run": "running",
    "obstacle_run": "running",
    # strength, yoga, mobility
    "strength_training": "strength_training",
    "indoor_cardio": "strength_training",
    "hiit": "strength_training",
    "pilates": "mobility",
    "yoga": "yoga",
    "mobility": "mobility",
    "flexibility_training": "mobility",
    "stretching": "mobility",
}

# A Garmin key may carry a version suffix, as stand_up_paddleboarding_v2 does.
_VERSION_SUFFIX = "_v2"


class SportNameError(Exception):
    """Raised when a sport name is not a string."""


def to_sport(value: Any) -> str:
    """Return the five-name sport a Garmin type key belongs to, or "other".

    A missing name is "other": an activity imported before the sport was stored,
    or a name Garmin did not supply. That is a real session without a type, not
    a programming error.
    """
    if value is None or value == "":
        return "other"
    if not isinstance(value, str):
        raise SportNameError("Sport must be text")
    key = value.strip().lower()
    if not key:
        return "other"
    if key.endswith(_VERSION_SUFFIX):
        key = key[: -len(_VERSION_SUFFIX)]
    return _BY_TYPE_KEY.get(key, "other")


def is_programmable(value: Any) -> bool:
    """Whether a workout can be built for this Garmin type key."""
    return to_sport(value) in SPORTS


__all__ = ["SPORTS", "SportNameError", "is_programmable", "to_sport"]
