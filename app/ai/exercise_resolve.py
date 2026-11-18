"""Resolve exercise names the catalog could not settle on its own.

Two situations need a second, narrow question rather than a guess:

- the catalog offered more than one name, and picking one would be arbitrary;
- the catalog offered nothing, so the movement may not exist there at all.

The question is deliberately small: it lists the movements asked about and, when
there is any, the catalog names on offer. Asking only this keeps the second call
cheap compared with re-sending the whole training context, and it keeps the
decision in the model's hands, where a substitution can be justified against the
athlete's constraint.

A movement with no answer is left unresolved on purpose. The caller decides what
a step it cannot name becomes; inventing a name here would send the athlete a
different exercise from the one that was prescribed.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai import client
from app.ai.exercise_match import describe_candidates

SYSTEM_PROMPT = """You match exercise names to a catalog of fixed names.

You receive a list of movements and, for each, either candidate names from the
catalog or no candidates at all.

Answer with one JSON object and nothing else:

{"choices": [{"query": "<the movement as given>",
              "match": "<one catalog name, or null>",
              "reason": "<short reason, or null>"}]}

Rules:
- "match" must be copied exactly from the candidates given for that movement.
  Never write a name that is not in its candidate list.
- When a movement has no candidates, answer null for it. Do not substitute a
  different exercise; another part of the app decides what to do with it.
- When several candidates fit, choose the one that is most likely to be the
  movement asked about, and say why in one short sentence.
- When none of the candidates fit, answer null.
"""


class ResolutionError(Exception):
    """Raised when the second question cannot be answered."""


def resolve(unresolved: list[Match]) -> dict[str, str | None]:
    """Return a chosen catalog name per query, or None where none fits."""
    if not unresolved:
        return {}
    payload = _question(unresolved)
    try:
        answer = client.chat(_messages(payload), _schema())
    except client.LlmError as error:
        raise ResolutionError(str(error)) from error
    return _read(answer, unresolved)


def _question(unresolved: list[Match]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in unresolved:
        # Both an ambiguous name and an unnamed one carry candidates: the first
        # because several names fit, the second because a few are close. A name
        # with no candidate at all still goes in, so the answer says so.
        item: dict[str, Any] = {
            "movement": match.query,
            "candidates": describe_candidates(match),
        }
        items.append(item)
    return items


def _messages(payload: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Resolve these movements as JSON.\n\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def _schema() -> dict[str, Any]:
    return {"required": ["choices"]}


def _read(answer: dict[str, Any], unresolved: list[Match]) -> dict[str, str | None]:
    choices = answer.get("choices")
    if not isinstance(choices, list):
        raise ResolutionError("Answer has no choices")
    allowed = {match.query: set(describe_candidates(match)) for match in unresolved}
    found: dict[str, str | None] = {match.query: None for match in unresolved}
    for item in choices:
        if not isinstance(item, dict):
            continue
        query = item.get("query")
        if not isinstance(query, str) or query not in allowed:
            # An answer about a movement nobody asked about is not usable.
            continue
        chosen = item.get("match")
        if chosen is None:
            found[query] = None
            continue
        if not isinstance(chosen, str) or chosen not in allowed[query]:
            # A name outside the offered list would defeat the whole point of
            # asking, so it is treated as no answer rather than accepted.
            found[query] = None
            continue
        found[query] = chosen
    return found


__all__ = ["ResolutionError", "SYSTEM_PROMPT", "resolve"]
