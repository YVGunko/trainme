ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "max_cadence_spm" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "avg_step_length_mm" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "total_descent_m" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "avg_vertical_ratio" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "avg_stance_time_percent" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "avg_stance_time_balance" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "avg_power_w" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "max_power_w" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "normalized_power_w" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "avg_respiration" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "max_respiration" DOUBLE PRECISION;
ALTER TABLE "running_activity" ADD COLUMN IF NOT EXISTS "total_strides" DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS "cycling_activity" (
    "activity_id" BIGINT NOT NULL,
    "avg_power_w" DOUBLE PRECISION,
    "max_power_w" DOUBLE PRECISION,
    "normalized_power_w" DOUBLE PRECISION,
    "intensity_factor" DOUBLE PRECISION,
    "tss" DOUBLE PRECISION,
    "avg_cadence_rpm" DOUBLE PRECISION,
    "max_cadence_rpm" DOUBLE PRECISION,
    "total_work_j" DOUBLE PRECISION,
    "threshold_power_w" DOUBLE PRECISION,
    "left_power_pct" DOUBLE PRECISION,
    "avg_left_torque_effectiveness" DOUBLE PRECISION,
    "avg_right_torque_effectiveness" DOUBLE PRECISION,
    "avg_left_pedal_smoothness" DOUBLE PRECISION,
    "avg_right_pedal_smoothness" DOUBLE PRECISION,
    "avg_combined_pedal_smoothness" DOUBLE PRECISION,
    "total_ascent_m" DOUBLE PRECISION,
    "total_descent_m" DOUBLE PRECISION,

    CONSTRAINT "cycling_activity_pkey" PRIMARY KEY ("activity_id")
);

CREATE TABLE IF NOT EXISTS "strength_set" (
    "activity_id" BIGINT NOT NULL,
    "set_index" INTEGER NOT NULL,
    "set_type" TEXT,
    "category" TEXT,
    "exercise" TEXT,
    "repetitions" DOUBLE PRECISION,
    "weight_kg" DOUBLE PRECISION,
    "duration_sec" DOUBLE PRECISION,
    "start_at" TIMESTAMPTZ(6),

    CONSTRAINT "strength_set_pkey" PRIMARY KEY ("activity_id","set_index")
);

CREATE TABLE IF NOT EXISTS "activity_field" (
    "activity_id" BIGINT NOT NULL,
    "message" TEXT NOT NULL,
    "message_index" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "ordinal" INTEGER NOT NULL,
    "value_num" DOUBLE PRECISION,
    "value_text" TEXT,
    "unit" TEXT,

    CONSTRAINT "activity_field_pkey" PRIMARY KEY ("activity_id","message","message_index","name","ordinal")
);

DO $$
BEGIN
    ALTER TABLE "cycling_activity"
        ADD CONSTRAINT "cycling_activity_activity_id_fkey"
        FOREIGN KEY ("activity_id") REFERENCES "activity"("id")
        ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "strength_set"
        ADD CONSTRAINT "strength_set_activity_id_fkey"
        FOREIGN KEY ("activity_id") REFERENCES "activity"("id")
        ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "activity_field"
        ADD CONSTRAINT "activity_field_activity_id_fkey"
        FOREIGN KEY ("activity_id") REFERENCES "activity"("id")
        ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
