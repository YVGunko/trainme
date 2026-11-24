import json
import os
from pathlib import Path
from typing import Any

import psycopg

from app.storage.crypto import decrypt, encrypt

_SCHEMA = """
CREATE TABLE IF NOT EXISTS garmin_account (
    id smallint PRIMARY KEY CHECK (id = 1),
    garmin_user_id bigint,
    encrypted_auth_data bytea NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw_object (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL,
    garmin_activity_id bigint,
    day date,
    source_format text NOT NULL,
    source_path text NOT NULL,
    source_sha256 text NOT NULL UNIQUE,
    byte_size integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


class DatabaseNotConfigured(Exception):
    """Raised when DATABASE_URL is missing."""


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise DatabaseNotConfigured
    return psycopg.connect(url)


# One session lock for schema changes and activity parsing. Parallel parses
# deadlock when several connections run ALTER TABLE at the same time.
_NORMALIZE_LOCK = 74821001


class normalize_lock:
    """Wait until no other request is parsing an activity or changing the schema."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def __enter__(self) -> "normalize_lock":
        self._connection.execute("SELECT pg_advisory_lock(%s)", (_NORMALIZE_LOCK,))
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        try:
            if exc_type is not None:
                self._connection.rollback()
            self._connection.execute("SELECT pg_advisory_unlock(%s)", (_NORMALIZE_LOCK,))
        except Exception:
            if exc_type is None:
                raise
        return False


def ensure_schema(connection: psycopg.Connection) -> None:
    with normalize_lock(connection):
        _execute_script(connection, _SCHEMA)
        migrations = sorted(
            (
                Path(__file__).resolve().parents[2] / "prisma" / "migrations"
            ).glob("*/migration.sql")
        )
        for migration in migrations:
            _execute_script(connection, migration.read_text())
        backfill_athlete_profile_hashes(connection)
        connection.commit()


def _execute_script(connection: psycopg.Connection, script: str) -> None:
    for statement in _split_sql(script):
        connection.execute(statement)


def _split_sql(script: str) -> list[str]:
    """Split a migration into statements on semicolons outside quotes and comments.

    A semicolon inside a comment or a dollar-quoted body is not a statement end,
    and splitting there produced garbage that failed only at execution time.
    """
    parts: list[str] = []
    current: list[str] = []
    in_dollar = False
    in_line_comment = False
    in_block_comment = False
    quote: str | None = None
    index = 0
    while index < len(script):
        if in_line_comment:
            current.append(script[index])
            if script[index] == "\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            if script.startswith("*/", index):
                current.append("*/")
                in_block_comment = False
                index += 2
                continue
            current.append(script[index])
            index += 1
            continue
        if quote is not None:
            current.append(script[index])
            if script[index] == quote:
                quote = None
            index += 1
            continue
        if script.startswith("--", index):
            in_line_comment = True
            current.append("--")
            index += 2
            continue
        if script.startswith("/*", index):
            in_block_comment = True
            current.append("/*")
            index += 2
            continue
        if script[index] in ("'", '"'):
            quote = script[index]
            current.append(script[index])
            index += 1
            continue
        if script.startswith("$$", index):
            in_dollar = not in_dollar
            current.append("$$")
            index += 2
            continue
        if script[index] == ";" and not in_dollar:
            statement = "".join(current).strip()
            if statement:
                parts.append(statement)
            current = []
            index += 1
            continue
        current.append(script[index])
        index += 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def load_token(connection: psycopg.Connection, key_material: str) -> str | None:
    row = connection.execute(
        "SELECT encrypted_auth_data FROM garmin_account WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    return decrypt(bytes(row[0]), key_material)


def save_token(
    connection: psycopg.Connection,
    token_json: str,
    garmin_user_id: int | None,
    key_material: str,
) -> None:
    payload = encrypt(token_json, key_material)
    connection.execute(
        """
        INSERT INTO garmin_account (id, garmin_user_id, encrypted_auth_data, updated_at)
        VALUES (1, %s, %s, now())
        ON CONFLICT (id) DO UPDATE
        SET garmin_user_id = EXCLUDED.garmin_user_id,
            encrypted_auth_data = EXCLUDED.encrypted_auth_data,
            updated_at = now()
        """,
        (garmin_user_id, payload),
    )
    connection.commit()


def find_activity_raw_object(
    connection: psycopg.Connection, garmin_activity_id: int
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT kind, garmin_activity_id, day::text, source_format, source_path, source_sha256, byte_size
        FROM raw_object
        WHERE kind = 'activity' AND garmin_activity_id = %s
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (garmin_activity_id,),
    ).fetchone()
    if row is None:
        return None
    return _raw_row(row)


def stored_days(connection: psycopg.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT DISTINCT day::text
        FROM raw_object
        WHERE kind = 'day' AND day IS NOT NULL
        ORDER BY 1
        """
    ).fetchall()
    return [row[0] for row in rows]


def find_day_raw_object(connection: psycopg.Connection, day: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT kind, garmin_activity_id, day::text, source_format, source_path, source_sha256, byte_size
        FROM raw_object
        WHERE kind = 'day' AND day = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (day,),
    ).fetchone()
    if row is None:
        return None
    return _raw_row(row)


def find_raw_object(connection: psycopg.Connection, sha256: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT kind, garmin_activity_id, day::text, source_format, source_path, source_sha256, byte_size
        FROM raw_object
        WHERE source_sha256 = %s
        """,
        (sha256,),
    ).fetchone()
    if row is None:
        return None
    return _raw_row(row)


def insert_raw_object(connection: psycopg.Connection, record: dict[str, Any]) -> dict[str, Any]:
    row = connection.execute(
        """
        INSERT INTO raw_object (
            kind, garmin_activity_id, day, source_format, source_path, source_sha256, byte_size
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_sha256) DO NOTHING
        RETURNING kind, garmin_activity_id, day::text, source_format, source_path, source_sha256, byte_size
        """,
        (
            record["kind"],
            record.get("garmin_activity_id"),
            record.get("day"),
            record["source_format"],
            record["source_path"],
            record["source_sha256"],
            record["byte_size"],
        ),
    ).fetchone()
    connection.commit()
    if row is None:
        existing = find_raw_object(connection, record["source_sha256"])
        if existing is None:
            raise RuntimeError("Raw object insert did not return a row")
        return existing
    return _raw_row(row)


def upsert_activity_meta(
    connection: psycopg.Connection,
    garmin_activity_id: int,
    garmin_name: str | None,
    start_local: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO activity_meta (garmin_activity_id, garmin_name, start_local)
        VALUES (%s, %s, %s)
        ON CONFLICT (garmin_activity_id) DO UPDATE
        SET garmin_name = COALESCE(EXCLUDED.garmin_name, activity_meta.garmin_name),
            start_local = COALESCE(EXCLUDED.start_local, activity_meta.start_local),
            updated_at = now()
        """,
        (garmin_activity_id, garmin_name, start_local),
    )
    connection.commit()


_HR_ZONE_COLUMNS = tuple(f"hr_zone_{zone}_sec" for zone in range(1, 6))
_POWER_ZONE_COLUMNS = tuple(f"power_zone_{zone}_sec" for zone in range(1, 8))


def save_hr_zone_seconds(
    connection: psycopg.Connection,
    garmin_activity_id: int,
    zones: dict[str, float],
) -> None:
    columns = [key for key in _HR_ZONE_COLUMNS if key in zones]
    if not columns:
        return
    values = [zones[key] for key in columns]
    column_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns)
    connection.execute(
        f"""
        INSERT INTO activity_meta (garmin_activity_id, {column_sql})
        VALUES (%s, {placeholders})
        ON CONFLICT (garmin_activity_id) DO UPDATE
        SET {assignments},
            updated_at = now()
        """,
        (garmin_activity_id, *values),
    )
    activity_assignments = ", ".join(f"{column} = %s" for column in columns)
    connection.execute(
        f"""
        UPDATE activity
        SET {activity_assignments}
        WHERE garmin_activity_id = %s
        """,
        (*values, garmin_activity_id),
    )
    connection.commit()


def save_power_zone_seconds(
    connection: psycopg.Connection,
    garmin_activity_id: int,
    zones: dict[str, float],
) -> None:
    columns = [key for key in _POWER_ZONE_COLUMNS if key in zones]
    if not columns:
        return
    values = [zones[key] for key in columns]
    column_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns)
    connection.execute(
        f"""
        INSERT INTO activity_meta (garmin_activity_id, {column_sql})
        VALUES (%s, {placeholders})
        ON CONFLICT (garmin_activity_id) DO UPDATE
        SET {assignments},
            updated_at = now()
        """,
        (garmin_activity_id, *values),
    )
    cycling_assignments = ", ".join(f"{column} = %s" for column in columns)
    connection.execute(
        f"""
        UPDATE cycling_activity
        SET {cycling_assignments}
        WHERE activity_id = (
            SELECT id FROM activity WHERE garmin_activity_id = %s
        )
        """,
        (*values, garmin_activity_id),
    )
    connection.commit()


def load_power_zone_seconds(
    connection: psycopg.Connection, garmin_activity_id: int
) -> dict[str, float]:
    quoted = ", ".join(_POWER_ZONE_COLUMNS)
    row = connection.execute(
        f"""
        SELECT {quoted}
        FROM activity_meta
        WHERE garmin_activity_id = %s
        """,
        (garmin_activity_id,),
    ).fetchone()
    if row is None:
        return {}
    found: dict[str, float] = {}
    for column, value in zip(_POWER_ZONE_COLUMNS, row):
        if value is not None:
            found[column] = float(value)
    return found


def load_hr_zone_seconds(
    connection: psycopg.Connection, garmin_activity_id: int
) -> dict[str, float]:
    row = connection.execute(
        """
        SELECT hr_zone_1_sec, hr_zone_2_sec, hr_zone_3_sec, hr_zone_4_sec, hr_zone_5_sec
        FROM activity_meta
        WHERE garmin_activity_id = %s
        """,
        (garmin_activity_id,),
    ).fetchone()
    if row is None:
        return {}
    found: dict[str, float] = {}
    for zone, value in enumerate(row, start=1):
        if value is not None:
            found[f"hr_zone_{zone}_sec"] = float(value)
    return found


def load_activity_meta(
    connection: psycopg.Connection, garmin_activity_id: int
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT garmin_name, title, description, to_char(start_local, 'YYYY-MM-DD HH24:MI:SS')
        FROM activity_meta
        WHERE garmin_activity_id = %s
        """,
        (garmin_activity_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "garmin_name": row[0],
        "title": row[1],
        "description": row[2],
        "start_local": row[3],
    }


def find_workout_import(
    connection: psycopg.Connection, source_sha256: str
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT garmin_workout_id, name, sport, scheduled_day::text, device_id,
               to_char(pushed_at, 'YYYY-MM-DD"T"HH24:MI:SS')
        FROM workout_import
        WHERE source_sha256 = %s
        """,
        (source_sha256,),
    ).fetchone()
    if row is None:
        return None
    return {
        "workout_id": row[0],
        "name": row[1],
        "sport": row[2],
        "date": row[3],
        "device_id": row[4],
        "pushed": row[5] is not None,
    }


def insert_workout_import(
    connection: psycopg.Connection,
    source_sha256: str,
    garmin_workout_id: int,
    name: str,
    sport: str,
) -> None:
    connection.execute(
        """
        INSERT INTO workout_import (source_sha256, garmin_workout_id, name, sport)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (source_sha256) DO NOTHING
        """,
        (source_sha256, garmin_workout_id, name, sport),
    )
    connection.commit()


def save_workout_delivery(
    connection: psycopg.Connection,
    garmin_workout_id: int,
    day: str | None,
    device_id: int | None,
) -> None:
    connection.execute(
        """
        UPDATE workout_import
        SET scheduled_day = COALESCE(%s::date, scheduled_day),
            device_id = COALESCE(%s, device_id),
            pushed_at = CASE WHEN %s IS NULL THEN pushed_at ELSE now() END
        WHERE garmin_workout_id = %s
        """,
        (day, device_id, device_id, garmin_workout_id),
    )
    connection.commit()


_PROFILE_COLUMNS = """
    recorded_at, notes, avoided_sports, birth_date::text, weight_kg, height_cm,
    cycling_ftp, hr_zones, power_zones, content_hash, source_sha256
"""


def load_latest_athlete_profile(connection: psycopg.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        f"""
        SELECT {_PROFILE_COLUMNS}
        FROM athlete_profile
        ORDER BY recorded_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return _profile_row(row)


def load_athlete_profile(connection: psycopg.Connection) -> dict[str, Any] | None:
    """Return the latest profile the coach can read, without storage bookkeeping."""
    latest = load_latest_athlete_profile(connection)
    if latest is None:
        return None
    return {
        "notes": latest["notes"],
        "avoided_sports": latest["avoided_sports"],
        "birth_date": latest["birth_date"],
        "weight_kg": latest["weight_kg"],
        "height_cm": latest["height_cm"],
        "cycling_ftp": latest["cycling_ftp"],
        "hr_zones": latest["hr_zones"],
        "power_zones": latest["power_zones"],
        "recorded_at": latest["recorded_at"],
    }


def insert_athlete_profile_version(
    connection: psycopg.Connection, version: dict[str, Any]
) -> dict[str, Any]:
    from psycopg.types.json import Json

    row = connection.execute(
        f"""
        INSERT INTO athlete_profile (
            recorded_at, notes, avoided_sports, birth_date, weight_kg, height_cm,
            cycling_ftp, hr_zones, power_zones, content_hash, source_sha256
        )
        VALUES (
            COALESCE(%s::timestamptz, clock_timestamp()),
            %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING {_PROFILE_COLUMNS}
        """,
        (
            version.get("recorded_at"),
            version.get("notes"),
            list(version.get("avoided_sports") or []),
            version.get("birth_date"),
            version.get("weight_kg"),
            version.get("height_cm"),
            version.get("cycling_ftp"),
            Json(version.get("hr_zones") or []),
            Json(version.get("power_zones") or []),
            version["content_hash"],
            version.get("source_sha256"),
        ),
    ).fetchone()
    connection.commit()
    return _profile_row(row)


def backfill_athlete_profile_hashes(connection: psycopg.Connection) -> None:
    """Fill fingerprints for rows migrated from the single-row profile table."""
    from app.profile_version import profile_hash

    rows = connection.execute(
        f"""
        SELECT {_PROFILE_COLUMNS}
        FROM athlete_profile
        WHERE content_hash IS NULL
        """
    ).fetchall()
    if not isinstance(rows, list):
        return
    for row in rows:
        version = _profile_row(row)
        connection.execute(
            """
            UPDATE athlete_profile
            SET content_hash = %s
            WHERE recorded_at = %s AND content_hash IS NULL
            """,
            (profile_hash(version), version["recorded_at"]),
        )


def _profile_row(row: tuple) -> dict[str, Any]:
    recorded_at = row[0]
    return {
        "recorded_at": recorded_at.isoformat() if hasattr(recorded_at, "isoformat") else recorded_at,
        "notes": row[1],
        "avoided_sports": list(row[2] or []),
        "birth_date": row[3],
        "weight_kg": None if row[4] is None else float(row[4]),
        "height_cm": None if row[5] is None else float(row[5]),
        "cycling_ftp": None if row[6] is None else float(row[6]),
        "hr_zones": row[7] if isinstance(row[7], list) else [],
        "power_zones": row[8] if isinstance(row[8], list) else [],
        "content_hash": row[9],
        "source_sha256": row[10],
    }


def upsert_activity_history(
    connection: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> int:
    """Store activity summaries, replacing a previous row for the same activity.

    Keyed on the Garmin activity id, so importing the same days twice updates the
    rows instead of duplicating them. That is what lets the cron re-read a
    rolling window every day.
    """
    if not rows:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO activity_history (
                garmin_activity_id, start_local, day, sport, duration_sec,
                distance_m, avg_hr, max_hr, calories, training_load,
                perceived_effort, feel, activity_note, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (garmin_activity_id) DO UPDATE
            SET start_local = EXCLUDED.start_local,
                day = EXCLUDED.day,
                sport = EXCLUDED.sport,
                duration_sec = EXCLUDED.duration_sec,
                distance_m = EXCLUDED.distance_m,
                avg_hr = COALESCE(EXCLUDED.avg_hr, activity_history.avg_hr),
                max_hr = COALESCE(EXCLUDED.max_hr, activity_history.max_hr),
                calories = COALESCE(EXCLUDED.calories, activity_history.calories),
                training_load = COALESCE(EXCLUDED.training_load, activity_history.training_load),
                perceived_effort = COALESCE(EXCLUDED.perceived_effort, activity_history.perceived_effort),
                feel = COALESCE(EXCLUDED.feel, activity_history.feel),
                activity_note = COALESCE(EXCLUDED.activity_note, activity_history.activity_note),
                updated_at = now()
            """,
            [
                (
                    row["garmin_activity_id"],
                    row["start_local"],
                    row["day"],
                    row["sport"],
                    row["duration_sec"],
                    row["distance_m"],
                    row["avg_hr"],
                    row["max_hr"],
                    row["calories"],
                    row["training_load"],
                    row.get("perceived_effort"),
                    row.get("feel"),
                    row.get("activity_note"),
                )
                for row in rows
            ],
        )
    connection.commit()
    return len(rows)


def stored_history_ids(
    connection: psycopg.Connection, ids: list[int]
) -> set[int]:
    """Return which of these activity ids already have a row.

    Used to skip the extra evaluation request for activities that are already
    stored with their rating, so a rolling window does not re-read them daily.
    """
    if not ids:
        return set()
    rows = connection.execute(
        "SELECT garmin_activity_id FROM activity_history WHERE garmin_activity_id = ANY(%s)",
        (ids,),
    ).fetchall()
    return {int(row[0]) for row in rows}


def load_activity_history(
    connection: psycopg.Connection,
    start: str,
    end: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Return stored activity summaries oldest first.

    Ascending order matters twice: a model reads the list as a timeline, and a
    LIMIT on a descending list would keep the oldest rows and drop the newest.
    """
    rows = connection.execute(
        """
        SELECT to_char(start_local, 'YYYY-MM-DD HH24:MI:SS'), day::text, sport,
               duration_sec, distance_m, avg_hr, max_hr, calories, training_load,
               perceived_effort, feel, activity_note
        FROM activity_history
        WHERE day >= %s::date AND day <= %s::date
        ORDER BY start_local ASC
        LIMIT %s
        """,
        (start, end, limit),
    ).fetchall()
    return [
        {
            "start_local": row[0],
            "day": row[1],
            "sport": row[2],
            "duration_sec": row[3],
            "distance_m": row[4],
            "avg_hr": row[5],
            "max_hr": row[6],
            "calories": row[7],
            "training_load": row[8],
            "perceived_effort": row[9],
            "feel": row[10],
            "activity_note": row[11],
        }
        for row in rows
    ]


def activity_history_count(connection: psycopg.Connection) -> int:
    row = connection.execute("SELECT count(*) FROM activity_history").fetchone()
    return int(row[0])


def load_recommendation(
    connection: psycopg.Connection, day: str
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT payload FROM daily_recommendation WHERE day = %s::date", (day,)
    ).fetchone()
    if row is None:
        return None
    payload = row[0]
    return payload if isinstance(payload, dict) else None


def load_active_recommendation(
    connection: psycopg.Connection, day: str
) -> dict[str, Any] | None:
    """Return the newest plan whose days still cover ``day``, or None.

    A plan is built for a stretch of days, so it stays in force until its last
    day has passed. Looking up by the day it was built would throw the week away
    every midnight.

    The stored fingerprint travels with the payload so a caller can decide
    whether the inputs that produced this plan still hold.
    """
    rows = connection.execute(
        """
        SELECT day::text, payload, input_fingerprint
        FROM daily_recommendation
        WHERE day <= %s::date
        ORDER BY day DESC
        LIMIT 8
        """,
        (day,),
    ).fetchall()
    for built_on, payload, fingerprint in rows:
        if not isinstance(payload, dict):
            continue
        days = payload.get("days")
        if not isinstance(days, list) or not days:
            continue
        last = days[-1].get("date") if isinstance(days[-1], dict) else None
        if isinstance(last, str) and last >= day:
            return payload | {
                "built_on": built_on,
                "input_fingerprint": fingerprint,
            }
    return None


def save_recommendation(
    connection: psycopg.Connection,
    day: str,
    payload: dict[str, Any],
    fingerprint: str | None = None,
) -> None:
    """Store the day's recommendation, keeping the first one written."""
    connection.execute(
        """
        INSERT INTO daily_recommendation (day, payload, input_fingerprint)
        VALUES (%s::date, %s::jsonb, %s)
        ON CONFLICT (day) DO NOTHING
        """,
        (day, json.dumps(payload, ensure_ascii=False), fingerprint),
    )
    connection.commit()


def replace_recommendation(
    connection: psycopg.Connection,
    day: str,
    payload: dict[str, Any],
    fingerprint: str | None = None,
) -> None:
    """Overwrite the day's recommendation, for an explicit regeneration."""
    connection.execute(
        """
        INSERT INTO daily_recommendation (day, payload, input_fingerprint)
        VALUES (%s::date, %s::jsonb, %s)
        ON CONFLICT (day) DO UPDATE
        SET payload = EXCLUDED.payload,
            input_fingerprint = EXCLUDED.input_fingerprint,
            created_at = now()
        """,
        (day, json.dumps(payload, ensure_ascii=False), fingerprint),
    )
    connection.commit()


_DAY_COLUMNS = (
    "resting_hr",
    "overnight_hrv",
    "hrv_status",
    "sleep_duration_sec",
    "sleep_score",
    "readiness_score",
    "readiness_level",
    "training_status",
    "garmin_load_acute",
    "garmin_load_chronic",
    "garmin_acwr",
)


def load_days(connection: psycopg.Connection, limit: int) -> list[dict[str, Any]]:
    """Return the most recent stored days, newest last, with their HRV value."""
    columns = ", ".join(_DAY_COLUMNS)
    rows = connection.execute(
        f"""
        SELECT to_char(date, 'YYYY-MM-DD'), {columns}
        FROM daily_metrics
        ORDER BY date DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    found = [{"date": row[0], **dict(zip(_DAY_COLUMNS, row[1:]))} for row in rows]
    return list(reversed(found))


def load_recent_days(
    connection: psycopg.Connection,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    """Return stored Garmin daily metrics, oldest first.

    A day with no row is a day that was never archived, so the caller must not
    read a gap as a recovered day.
    """
    rows = connection.execute(
        """
        SELECT to_char(date, 'YYYY-MM-DD'),
               resting_hr, overnight_hrv, hrv_status,
               sleep_duration_sec, sleep_score,
               readiness_score, readiness_level, training_status,
               vo2max_generic, vo2max_cycling,
               garmin_load_acute, garmin_load_chronic, garmin_acwr,
               monthly_load_aerobic_low, monthly_load_aerobic_high,
               monthly_load_anaerobic
        FROM daily_metrics
        WHERE date >= %s::date AND date <= %s::date
        ORDER BY date ASC
        """,
        (start, end),
    ).fetchall()
    keys = (
        "resting_hr",
        "overnight_hrv",
        "hrv_status",
        "sleep_duration_sec",
        "sleep_score",
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
    )
    return [{"date": row[0], **dict(zip(keys, row[1:]))} for row in rows]


def load_subjective_days(
    connection: psycopg.Connection,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    """Return the wellness row per day, including the athlete's own note.

    The note is included because the athlete asked for it to reach the coach: it
    is where a flare-up gets described in words, and the scored 1-4 fields alone
    cannot say which body part hurt.
    """
    rows = connection.execute(
        """
        SELECT to_char(date, 'YYYY-MM-DD'),
               fatigue, soreness, mood, motivation, stress, sleep_quality, injury, illness,
               note, evening_note, coach_request
        FROM subjective_log
        WHERE date >= %s::date AND date <= %s::date
        ORDER BY date ASC
        """,
        (start, end),
    ).fetchall()
    keys = ("fatigue", "soreness", "mood", "motivation", "stress", "sleep_quality", "injury", "illness")
    return [
        {
            "date": row[0],
            **dict(zip(keys, row[1:9])),
            "note": row[9],
            "evening_note": row[10],
            "coach_request": row[11],
        }
        for row in rows
    ]


def _raw_row(row: tuple) -> dict[str, Any]:
    return {
        "kind": row[0],
        "garmin_activity_id": row[1],
        "day": row[2],
        "source_format": row[3],
        "source_path": row[4],
        "source_sha256": row[5],
        "byte_size": row[6],
    }
