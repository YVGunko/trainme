CREATE TABLE IF NOT EXISTS athlete_profile (
    id smallint PRIMARY KEY CHECK (id = 1),
    notes text,
    avoided_sports text[] NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT athlete_profile_notes_check CHECK (notes IS NULL OR char_length(notes) <= 4000)
);
