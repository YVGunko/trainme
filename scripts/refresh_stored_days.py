"""Refresh daily Garmin metrics for days already stored in Postgres.

Sleep and heart-rate files are reused. Activity ZIP files are not downloaded.
Token JSON is never printed.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.garmin.archive import refresh_stored_days  # noqa: E402
from app.garmin.client import GarminNotConfigured  # noqa: E402
from app.storage.crypto import EncryptionKeyMissing  # noqa: E402
from app.storage.db import DatabaseNotConfigured, connect  # noqa: E402
from garminconnect import GarminConnectAuthenticationError  # noqa: E402


_COLUMNS = (
    "hrv_status",
    "readiness_score",
    "readiness_level",
    "training_status",
    "vo2max_generic",
    "vo2max_cycling",
    "garmin_load_acute",
    "garmin_load_chronic",
    "garmin_acwr",
    "monthly_load_aerobic_low",
    "monthly_load_aerobic_high",
    "monthly_load_anaerobic",
    "sleep_duration_sec",
    "sleep_score",
    "overnight_hrv",
    "resting_hr",
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("garminconnect").setLevel(logging.ERROR)
    try:
        result = refresh_stored_days()
    except (DatabaseNotConfigured, EncryptionKeyMissing, GarminNotConfigured) as exc:
        print(f"refresh stopped: {type(exc).__name__}")
        return 2
    except GarminConnectAuthenticationError:
        print("refresh stopped: GarminConnectAuthenticationError")
        return 2

    summary = {
        "day_count": result["day_count"],
        "refreshed_count": result["refreshed_count"],
        "failed": result["failed"],
        "sleep_downloaded": [item["day"] for item in result["days"] if item["sleep_downloaded"]],
        "rows": _rows(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if not result["failed"] else 1


def _rows() -> list[dict[str, object]]:
    quoted = ", ".join(_COLUMNS)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT date::text, {quoted}
            FROM daily_metrics
            ORDER BY date
            """
        ).fetchall()
    names = ("date", *_COLUMNS)
    return [dict(zip(names, row)) for row in rows]


if __name__ == "__main__":
    raise SystemExit(main())
