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


def ensure_schema(connection: psycopg.Connection) -> None:
    _execute_script(connection, _SCHEMA)
    migration = (
        Path(__file__).resolve().parents[2]
        / "prisma"
        / "migrations"
        / "20261010120000_normalize_activity"
        / "migration.sql"
    )
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
