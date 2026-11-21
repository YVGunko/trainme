-- The single id=1 profile row becomes the first version. Notes and excluded
-- sports are copied. Garmin fields start empty and are filled on the next sync
-- only when their fingerprint differs.
DO $$
DECLARE
  constraint_name text;
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'athlete_profile'
      AND column_name = 'id'
  ) THEN
    FOR constraint_name IN
      SELECT con.conname
      FROM pg_constraint con
      JOIN pg_class rel ON rel.oid = con.conrelid
      JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
      WHERE nsp.nspname = 'public'
        AND rel.relname = 'athlete_profile'
        AND con.contype = 'c'
        AND pg_get_constraintdef(con.oid) ILIKE '%(id%'
    LOOP
      EXECUTE format('ALTER TABLE athlete_profile DROP CONSTRAINT %I', constraint_name);
    END LOOP;

    ALTER TABLE athlete_profile DROP CONSTRAINT IF EXISTS athlete_profile_pkey;
    ALTER TABLE athlete_profile ADD COLUMN recorded_at timestamptz;
    UPDATE athlete_profile
    SET recorded_at = COALESCE(updated_at, clock_timestamp())
    WHERE recorded_at IS NULL;
    ALTER TABLE athlete_profile DROP COLUMN id;
    ALTER TABLE athlete_profile DROP COLUMN updated_at;
    ALTER TABLE athlete_profile ALTER COLUMN recorded_at SET NOT NULL;
    ALTER TABLE athlete_profile ADD PRIMARY KEY (recorded_at);
    ALTER TABLE athlete_profile ADD COLUMN birth_date date;
    ALTER TABLE athlete_profile ADD COLUMN weight_kg double precision;
    ALTER TABLE athlete_profile ADD COLUMN height_cm double precision;
    ALTER TABLE athlete_profile ADD COLUMN cycling_ftp double precision;
    ALTER TABLE athlete_profile ADD COLUMN hr_zones jsonb NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE athlete_profile ADD COLUMN power_zones jsonb NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE athlete_profile ADD COLUMN content_hash text;
    ALTER TABLE athlete_profile ADD COLUMN source_sha256 text;
  END IF;
END $$;
