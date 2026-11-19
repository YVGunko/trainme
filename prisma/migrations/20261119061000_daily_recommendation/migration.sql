-- One recommendation per day, so the morning and evening runs agree.
CREATE TABLE IF NOT EXISTS daily_recommendation (
    day date PRIMARY KEY,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
