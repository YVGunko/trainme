-- The input the plan was built from, so an unchanged input is not re-asked.
ALTER TABLE daily_recommendation ADD COLUMN IF NOT EXISTS input_fingerprint text;
