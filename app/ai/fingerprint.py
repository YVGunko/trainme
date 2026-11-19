"""Recognise when the coach would be given the same data twice.

The cron runs at 11:00 and 23:00. Often nothing has changed in between: no
session finished, no metric arrived, no wellness row was edited. Asking the model
then produces a rewritten week from identical input, which costs tokens and makes
the plan look unstable for no reason.

The fingerprint covers what the model actually reads, and nothing else. Time of
day, the plan already stored, and the day itself are excluded on purpose: the day
is already part of the hash through the data it holds, and including a clock or
an existing plan would make every call look different.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Sections of the context that feed the decision. A field added to the context
# but not here would let a stale plan survive a real change, so this list mirrors
# build_context deliberately and a test compares them.
_FINGERPRINT_SECTIONS = (
    "profile",
    "recent_days",
    "wellness",
    "recent_activities",
    "weekly_totals",
)


def context_fingerprint(context: dict[str, Any]) -> str:
    """Return a stable hash of the parts of a context that decide the plan."""
    document = {key: context.get(key) for key in _FINGERPRINT_SECTIONS}
    # The plan start is the only date that matters: a plan for a later day is a
    # different question even with identical history.
    document["plan_start"] = context.get("today")
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


__all__ = ["context_fingerprint"]
