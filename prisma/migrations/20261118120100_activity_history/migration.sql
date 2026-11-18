CREATE TABLE IF NOT EXISTS activity_history (
    garmin_activity_id bigint PRIMARY KEY,
    start_local timestamp without time zone NOT NULL,
    day date NOT NULL,
    sport text,
    duration_sec double precision,
    distance_m double precision,
    avg_hr double precision,
    max_hr double precision,
    calories double precision,
    training_load double precision,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS activity_history_day_idx ON activity_history (day DESC);
