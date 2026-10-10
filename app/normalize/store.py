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

_RUNNING_COLUMNS = (
    "avg_cadence_spm",
    "max_cadence_spm",
    "avg_step_length_mm",
    "avg_stride_length_cm",
    "elevation_gain_m",
    "total_descent_m",
    "avg_ground_contact_time_ms",
    "avg_vertical_oscillation_cm",
    "avg_vertical_ratio",
    "avg_stance_time_percent",
    "avg_stance_time_balance",
    "avg_power_w",
    "max_power_w",
    "normalized_power_w",
    "avg_respiration",
    "max_respiration",
    "total_strides",
)

_CYCLING_COLUMNS = (
    "avg_power_w",
    "max_power_w",
    "normalized_power_w",
    "intensity_factor",
    "tss",
    "avg_cadence_rpm",
    "max_cadence_rpm",
    "total_work_j",
    "threshold_power_w",
    "left_power_pct",
    "avg_left_torque_effectiveness",
    "avg_right_torque_effectiveness",
    "avg_left_pedal_smoothness",
    "avg_right_pedal_smoothness",
    "avg_combined_pedal_smoothness",
    "total_ascent_m",
    "total_descent_m",
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
    field_count = _replace_fields(connection, activity_id, parsed["fields"])
    running = parsed["running"]
    cycling = parsed["cycling"]
    sets = parsed["sets"]
    if running is None:
        connection.execute("DELETE FROM running_activity WHERE activity_id = %s", (activity_id,))
    else:
        _upsert_keyed(connection, "running_activity", activity_id, _RUNNING_COLUMNS, running)
    if cycling is None:
        connection.execute("DELETE FROM cycling_activity WHERE activity_id = %s", (activity_id,))
    else:
        _upsert_keyed(connection, "cycling_activity", activity_id, _CYCLING_COLUMNS, cycling)
    set_count = _replace_sets(connection, activity_id, sets)
    written_fields = _upsert_day(connection, day, day_fields, day_source)
    connection.commit()
    session_fields = sorted(
        {row["name"] for row in parsed["fields"] if row["message"] == "session"}
    )
    return {
        "activity": {
            "garmin_activity_id": garmin_activity_id,
            "sport": parsed["sport"],
            "sub_sport": parsed["sub_sport"],
            "sample_count": sample_count,
            "field_count": field_count,
            "session_fields": session_fields,
            "running_activity": running is not None,
            "cycling_activity": cycling is not None,
            "strength_set_count": set_count,
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
        "garmin_activity_load": parsed["garmin_activity_load"],
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


def _upsert_keyed(
    connection: psycopg.Connection,
    table: str,
    activity_id: int,
    columns: tuple[str, ...],
    values: dict[str, Any],
) -> None:
    quoted = ", ".join(columns)
    placeholders = ", ".join(["%s"] * (len(columns) + 1))
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns)
    connection.execute(
        f"""
        INSERT INTO {table} (activity_id, {quoted})
        VALUES ({placeholders})
        ON CONFLICT (activity_id) DO UPDATE
        SET {assignments}
        """,
        (activity_id, *[values.get(column) for column in columns]),
    )


def _replace_fields(connection: psycopg.Connection, activity_id: int, fields: list[dict[str, Any]]) -> int:
    connection.execute("DELETE FROM activity_field WHERE activity_id = %s", (activity_id,))
    if not fields:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO activity_field (
                activity_id, message, message_index, name, ordinal, value_num, value_text, unit
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    activity_id,
                    row["message"],
                    row["message_index"],
                    row["name"],
                    row["ordinal"],
                    row["value_num"],
                    row["value_text"],
                    row["unit"],
                )
                for row in fields
            ],
        )
    return len(fields)


def _replace_sets(connection: psycopg.Connection, activity_id: int, sets: list[dict[str, Any]]) -> int:
    connection.execute("DELETE FROM strength_set WHERE activity_id = %s", (activity_id,))
    if not sets:
        return 0
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO strength_set (
                activity_id, set_index, set_type, category, exercise,
                repetitions, weight_kg, duration_sec, start_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    activity_id,
                    row["set_index"],
                    row["set_type"],
                    row["category"],
                    row["exercise"],
                    row["repetitions"],
                    row["weight_kg"],
                    row["duration_sec"],
                    row["start_at"],
                )
                for row in sets
            ],
        )
    return len(sets)


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
