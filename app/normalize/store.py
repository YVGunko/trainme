from datetime import date
from typing import Any

import psycopg

_ACTIVITY_COLUMNS = (
    "garmin_activity_id",
    "sport",
    "sub_sport",
    "garmin_type_key",
    "start_at",
    "end_at",
    "duration_sec",
    "moving_duration_sec",
    "elapsed_duration_sec",
    "timezone_offset_min",
    "distance_m",
    "avg_hr",
    "max_hr",
    "avg_speed",
    "calories",
    "aerobic_effect",
    "anaerobic_effect",
    "training_effect_label",
    "garmin_activity_load",
    "hr_zone_1_sec",
    "hr_zone_2_sec",
    "hr_zone_3_sec",
    "hr_zone_4_sec",
    "hr_zone_5_sec",
    "source",
    "source_format",
    "source_path",
    "source_sha256",
)

_DAY_COLUMNS = (
    "sleep_duration_sec",
    "sleep_score",
    "overnight_hrv",
    "resting_hr",
)


def latest_raw_object(
    connection: psycopg.Connection, kind: str, source_format: str
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT kind, garmin_activity_id, day::text, source_format, source_path, source_sha256, byte_size
        FROM raw_object
        WHERE kind = %s AND source_format = %s
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (kind, source_format),
    ).fetchone()
    if row is None:
        return None
    return {
        "kind": row[0],
        "garmin_activity_id": row[1],
        "day": row[2],
        "source_format": row[3],
        "source_path": row[4],
        "source_sha256": row[5],
        "byte_size": row[6],
    }


def write_normalized(
    connection: psycopg.Connection,
    *,
    garmin_activity_id: int,
    parsed: dict[str, Any],
    activity_source: dict[str, Any],
    day: date,
    day_fields: dict[str, float],
    day_source: dict[str, Any],
) -> dict[str, Any]:
    activity_id = _upsert_activity(connection, garmin_activity_id, parsed, activity_source)
    sample_count = _replace_samples(connection, activity_id, parsed["samples"])
    running = parsed["running"]
    if running is None:
        connection.execute("DELETE FROM running_activity WHERE activity_id = %s", (activity_id,))
    else:
        _upsert_running(connection, activity_id, running)
    written_fields = _upsert_day(connection, day, day_fields, day_source)
    connection.commit()
    return {
        "activity": {
            "garmin_activity_id": garmin_activity_id,
            "sport": parsed["sport"],
            "sample_count": sample_count,
            "running_activity": running is not None,
            "source_sha256": activity_source["source_sha256"],
        },
        "day": {"date": day.isoformat(), "fields": written_fields},
    }


def _upsert_activity(
    connection: psycopg.Connection,
    garmin_activity_id: int,
    parsed: dict[str, Any],
    source: dict[str, Any],
) -> int:
    values = {
        "garmin_activity_id": garmin_activity_id,
        "sport": parsed["sport"],
        "sub_sport": parsed["sub_sport"],
        "garmin_type_key": None,
        "start_at": parsed["start_at"],
        "end_at": parsed["end_at"],
        "duration_sec": parsed["duration_sec"],
        "moving_duration_sec": parsed["moving_duration_sec"],
        "elapsed_duration_sec": parsed["elapsed_duration_sec"],
        "timezone_offset_min": parsed["timezone_offset_min"],
        "distance_m": parsed["distance_m"],
        "avg_hr": parsed["avg_hr"],
        "max_hr": parsed["max_hr"],
        "avg_speed": parsed["avg_speed"],
        "calories": parsed["calories"],
        "aerobic_effect": parsed["aerobic_effect"],
        "anaerobic_effect": parsed["anaerobic_effect"],
        "training_effect_label": None,
        "garmin_activity_load": None,
        "source": "garmin",
        "source_format": source["source_format"],
        "source_path": source["source_path"],
        "source_sha256": source["source_sha256"],
    }
    for zone in range(1, 6):
        values[f"hr_zone_{zone}_sec"] = parsed.get(f"hr_zone_{zone}_sec")
    columns = ", ".join(_ACTIVITY_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_ACTIVITY_COLUMNS))
    assignments = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in _ACTIVITY_COLUMNS
        if column != "garmin_activity_id"
    )
    row = connection.execute(
        f"""
        INSERT INTO activity ({columns})
        VALUES ({placeholders})
        ON CONFLICT (garmin_activity_id) DO UPDATE
        SET {assignments}
        RETURNING id
        """,
        tuple(values[column] for column in _ACTIVITY_COLUMNS),
    ).fetchone()
    if row is None:
        raise RuntimeError("Activity insert did not return an id")
    return int(row[0])


def _upsert_running(connection: psycopg.Connection, activity_id: int, running: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO running_activity (
            activity_id, avg_cadence_spm, elevation_gain_m,
            avg_ground_contact_time_ms, avg_vertical_oscillation_cm, avg_stride_length_cm
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (activity_id) DO UPDATE
        SET avg_cadence_spm = EXCLUDED.avg_cadence_spm,
            elevation_gain_m = EXCLUDED.elevation_gain_m,
            avg_ground_contact_time_ms = EXCLUDED.avg_ground_contact_time_ms,
            avg_vertical_oscillation_cm = EXCLUDED.avg_vertical_oscillation_cm,
            avg_stride_length_cm = EXCLUDED.avg_stride_length_cm
        """,
        (
            activity_id,
            running.get("avg_cadence_spm"),
            running.get("elevation_gain_m"),
            running.get("avg_ground_contact_time_ms"),
            running.get("avg_vertical_oscillation_cm"),
            running.get("avg_stride_length_cm"),
        ),
    )


def _replace_samples(connection: psycopg.Connection, activity_id: int, samples: list[dict[str, Any]]) -> int:
    connection.execute("DELETE FROM activity_sample WHERE activity_id = %s", (activity_id,))
    if not samples:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO activity_sample (activity_id, timestamp, metric, value, unit)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (activity_id, sample["timestamp"], sample["metric"], sample["value"], sample["unit"])
                for sample in samples
            ],
        )
    return len(samples)


def _upsert_day(
    connection: psycopg.Connection,
    day: date,
    fields: dict[str, float],
    source: dict[str, Any],
) -> list[str]:
    columns = ["date", "source_format", "source_path", "source_sha256"]
    values: list[Any] = [day, source["source_format"], source["source_path"], source["source_sha256"]]
    written = [key for key in _DAY_COLUMNS if key in fields]
    for key in written:
        columns.append(key)
        values.append(fields[key])
    assignments = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column != "date"
    )
    quoted = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    connection.execute(
        f"""
        INSERT INTO daily_metrics ({quoted})
        VALUES ({placeholders})
        ON CONFLICT (date) DO UPDATE
        SET {assignments}
        """,
        tuple(values),
    )
    return written
