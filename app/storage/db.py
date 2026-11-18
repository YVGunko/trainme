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
        connection.commit()


def _execute_script(connection: psycopg.Connection, script: str) -> None:
    for statement in _split_sql(script):
        connection.execute(statement)


def _split_sql(script: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_dollar = False
    index = 0
    while index < len(script):
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


def load_athlete_profile(connection: psycopg.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT notes, avoided_sports FROM athlete_profile WHERE id = 1"
    ).fetchone()
    if row is None:
        return None
    return {"notes": row[0], "avoided_sports": list(row[1] or [])}


def save_athlete_profile(
    connection: psycopg.Connection,
    notes: str | None,
    avoided_sports: list[str],
) -> dict[str, Any]:
    row = connection.execute(
        """
        INSERT INTO athlete_profile (id, notes, avoided_sports)
        VALUES (1, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET notes = EXCLUDED.notes,
            avoided_sports = EXCLUDED.avoided_sports,
            updated_at = now()
        RETURNING notes, avoided_sports
        """,
        (notes, avoided_sports),
    ).fetchone()
    connection.commit()
    return {"notes": row[0], "avoided_sports": list(row[1] or [])}


def upsert_activity_history(
    connection: psycopg.Connection,
    rows: list[dict[str, Any]],
) -> int:
    """Store activity summaries, replacing a previous row for the same activity."""
    if not rows:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO activity_history (
                garmin_activity_id, start_local, day, sport, duration_sec,
                distance_m, avg_hr, max_hr, calories, training_load, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
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
                )
                for row in rows
            ],
        )
    connection.commit()
    return len(rows)


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
               duration_sec, distance_m, avg_hr, max_hr, calories, training_load
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
        }
        for row in rows
    ]


def activity_history_count(connection: psycopg.Connection) -> int:
    row = connection.execute("SELECT count(*) FROM activity_history").fetchone()
    return int(row[0])


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
    """Return the scored wellness row per day. The free-text note is not read.

    The note is what the athlete writes for themselves; it is deliberately left
    in the table so it cannot reach a model by accident.
    """
    rows = connection.execute(
        """
        SELECT to_char(date, 'YYYY-MM-DD'),
               fatigue, soreness, mood, motivation, stress, sleep_quality, injury, illness
        FROM subjective_log
        WHERE date >= %s::date AND date <= %s::date
        ORDER BY date ASC
        """,
        (start, end),
    ).fetchall()
    keys = ("fatigue", "soreness", "mood", "motivation", "stress", "sleep_quality", "injury", "illness")
    return [{"date": row[0], **dict(zip(keys, row[1:]))} for row in rows]


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
