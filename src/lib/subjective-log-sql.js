export const CREATE_SUBJECTIVE_LOG = `CREATE TABLE IF NOT EXISTS subjective_log (
    date date PRIMARY KEY,
    fatigue smallint,
    soreness smallint,
    mood smallint,
    motivation smallint,
    stress smallint,
    sleep_quality smallint,
    injury smallint,
    illness smallint,
    note text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT subjective_log_fatigue_check CHECK (fatigue IS NULL OR (fatigue BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_soreness_check CHECK (soreness IS NULL OR (soreness BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_mood_check CHECK (mood IS NULL OR (mood BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_motivation_check CHECK (motivation IS NULL OR (motivation BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_stress_check CHECK (stress IS NULL OR (stress BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_sleep_quality_check CHECK (sleep_quality IS NULL OR (sleep_quality BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_injury_check CHECK (injury IS NULL OR (injury BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_illness_check CHECK (illness IS NULL OR (illness BETWEEN 1 AND 4)),
    CONSTRAINT subjective_log_note_check CHECK (note IS NULL OR char_length(note) <= 4000)
);`;

// Columns added after the first table. CREATE IF NOT EXISTS does not add them
// to a table that already exists, so a day save runs these as well.
export const EXTEND_SUBJECTIVE_LOG = [
  `ALTER TABLE subjective_log ADD COLUMN IF NOT EXISTS evening_note text`,
  `ALTER TABLE subjective_log ADD COLUMN IF NOT EXISTS coach_request text`,
  `DO $$
BEGIN
    ALTER TABLE subjective_log
        ADD CONSTRAINT subjective_log_evening_note_check
        CHECK (evening_note IS NULL OR char_length(evening_note) <= 4000);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$`,
  `DO $$
BEGIN
    ALTER TABLE subjective_log
        ADD CONSTRAINT subjective_log_coach_request_check
        CHECK (coach_request IS NULL OR char_length(coach_request) <= 4000);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$`,
];
