"""Match an exercise the model named in plain language to the Garmin catalog.

The model writes "Glute Bridge" or "Nordic Hamstring Curl". The catalog holds
1527 fixed names ("Banded Glute Bridge", "Single-leg Standing Dumbbell Calf
Raise"), and a workout is refused outright for a name that is not one of them.
So the answer is matched here, by code, rather than trusted.

Matching is layered and stops at the first layer that settles it:

1. same words in the same order — the model named it exactly;
2. every word present — one candidate settles it;
3. the same but preferring the shortest name — settles "Hip Abduction";
4. otherwise the caller gets the candidates and asks a narrower question.

A name with no candidate is not an error to guess around: the catalog simply has
no such movement, and the caller has to decide what to do with the step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from garminconnect import exercises

# Outcomes a match can end in. "ambiguous" and "missing" are the only two that
# need a second question.
EXACT = "exact"
CLOSEST = "closest"
AMBIGUOUS = "ambiguous"
MISSING = "missing"

_WORDS = re.compile(r"[^a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return [word for word in _WORDS.split(text.lower()) if word]


# The catalog is fixed at import time; building this once keeps a match cheap
# when a plan names twenty exercises.
_CATALOG: list[tuple[dict[str, str], list[str]]] = [
    (entry, _tokens(entry["name"])) for entry in exercises.EXERCISES
]


@dataclass
class Match:
    """What the catalog offered for one name the model wrote."""

    query: str
    outcome: str
    entry: dict[str, str] | None = None
    candidates: list[dict[str, str]] = field(default_factory=list)

    @property
    def settled(self) -> bool:
        return self.entry is not None

    @property
    def needs_question(self) -> bool:
        """True when the caller must ask, because no single name was chosen."""
        if self.settled:
            return False
        return self.outcome in {AMBIGUOUS, MISSING}


def match_exercise(name: Any) -> Match:
    """Return the catalog entry for a plain-language name, or the candidates."""
    query = name.strip() if isinstance(name, str) else ""
    wanted = _tokens(query)
    if not wanted:
        return Match(query=query, outcome=MISSING)

    same_order = [entry for entry, words in _CATALOG if words == wanted]
    if len(same_order) == 1:
        return Match(query=query, outcome=EXACT, entry=same_order[0])

    present = [entry for entry, words in _CATALOG if all(word in words for word in wanted)]
    if len(present) == 1:
        # One candidate is not ambiguity, whatever the layer.
        return Match(query=query, outcome=EXACT, entry=present[0])
    if present:
        shortest = min(len(_tokens(entry["name"])) for entry in present)
        core = [entry for entry in present if len(_tokens(entry["name"])) == shortest]
        if len(core) == 1:
            return Match(query=query, outcome=CLOSEST, entry=core[0])
        return Match(query=query, outcome=AMBIGUOUS, candidates=_sorted(core))

    # A word-subset search is deliberately not used here: matching "Nordic
    # Hamstring Curl" to any name sharing one word would invent a movement the
    # athlete did not ask for, which is worse than asking.
    return Match(query=query, outcome=MISSING)


def _sorted(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(entries, key=lambda entry: (len(entry["name"]), entry["name"]))


def describe_candidates(match: Match, limit: int = 8) -> list[str]:
    """Return catalog names to offer back, shortest first and bounded."""
    return [entry["name"] for entry in _sorted(match.candidates)[:limit]]


__all__ = [
    "AMBIGUOUS",
    "CLOSEST",
    "EXACT",
    "MISSING",
    "Match",
    "describe_candidates",
    "match_exercise",
]
