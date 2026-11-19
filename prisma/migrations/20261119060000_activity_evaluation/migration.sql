-- The athlete's own verdict on a finished session, read from Garmin.
ALTER TABLE activity_history ADD COLUMN IF NOT EXISTS perceived_effort smallint;
ALTER TABLE activity_history ADD COLUMN IF NOT EXISTS feel smallint;
ALTER TABLE activity_history ADD COLUMN IF NOT EXISTS activity_note text;

-- Garmin stores perceived effort as 10-100, so this app keeps the 1-10 the
-- athlete entered. A value outside that range means a bad read, not a rating.
ALTER TABLE activity_history
    DROP CONSTRAINT IF EXISTS activity_history_perceived_effort_check;
ALTER TABLE activity_history
    ADD CONSTRAINT activity_history_perceived_effort_check
    CHECK (perceived_effort IS NULL OR (perceived_effort BETWEEN 1 AND 10));

-- "How did you feel?" is one of five points, from very weak to very strong.
ALTER TABLE activity_history DROP CONSTRAINT IF EXISTS activity_history_feel_check;
ALTER TABLE activity_history
    ADD CONSTRAINT activity_history_feel_check
    CHECK (feel IS NULL OR feel IN (0, 25, 50, 75, 100));
