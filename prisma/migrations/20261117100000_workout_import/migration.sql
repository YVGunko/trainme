CREATE TABLE IF NOT EXISTS workout_import (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_sha256 text NOT NULL UNIQUE,
    garmin_workout_id bigint NOT NULL UNIQUE,
    name text NOT NULL,
    sport text NOT NULL,
    scheduled_day date,
    device_id bigint,
    pushed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
