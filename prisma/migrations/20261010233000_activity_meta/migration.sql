CREATE TABLE IF NOT EXISTS activity_meta (
    garmin_activity_id bigint PRIMARY KEY,
    garmin_name text,
    title text,
    description text,
    start_local timestamp without time zone,
    updated_at timestamptz NOT NULL DEFAULT now()
);
