"""Read and validate the athlete profile.

The profile is what the athlete writes once, on purpose, for the coach: recurring
problems, movements that need attention, sports to stay away from. It is not the
daily wellness note, which stays in the database and never reaches a model.
"""

from __future__ import annotations

from typing import Any

# Sports the workout builder can send. A profile may only avoid a sport the app
# understands, so a typo cannot silently become an avoidance of nothing.
KNOWN_SPORTS = ("running", "cycling", "strength_training", "yoga", "mobility")

_MAX_NOTES = 4000


class ProfileError(Exception):
    """Raised when a profile cannot be stored."""


def parse_profile(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ProfileError("Profile must be an object")
    unknown = sorted(set(body) - {"notes", "avoided_sports"})
    if unknown:
        raise ProfileError(f"Unknown profile field: {unknown[0]}")
    return {
        "notes": _notes(body.get("notes")),
        "avoided_sports": _sports(body.get("avoided_sports")),
    }


def _notes(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileError("Notes must be text")
    text = value.strip()
    if not text:
        return None
    if len(text) > _MAX_NOTES:
        raise ProfileError(f"Notes are longer than {_MAX_NOTES} characters")
    return text


def _sports(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileError("avoided_sports must be a list")
    found: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in KNOWN_SPORTS:
            raise ProfileError(f"Unknown sport: {item}")
        if item not in found:
            found.append(item)
    return found


__all__ = ["KNOWN_SPORTS", "ProfileError", "parse_profile"]
