ALTER TABLE subjective_log ADD COLUMN IF NOT EXISTS evening_note text;
ALTER TABLE subjective_log ADD COLUMN IF NOT EXISTS coach_request text;
DO $$
BEGIN
    ALTER TABLE subjective_log
        ADD CONSTRAINT subjective_log_evening_note_check
        CHECK (evening_note IS NULL OR char_length(evening_note) <= 4000);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
DO $$
BEGIN
    ALTER TABLE subjective_log
        ADD CONSTRAINT subjective_log_coach_request_check
        CHECK (coach_request IS NULL OR char_length(coach_request) <= 4000);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
