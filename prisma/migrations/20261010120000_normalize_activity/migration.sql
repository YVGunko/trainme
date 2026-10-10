-- CreateTable
CREATE TABLE IF NOT EXISTS "activity" (
    "id" BIGSERIAL NOT NULL,
    "garmin_activity_id" BIGINT NOT NULL,
    "sport" TEXT,
    "sub_sport" TEXT,
    "garmin_type_key" TEXT,
    "start_at" TIMESTAMPTZ(6),
    "end_at" TIMESTAMPTZ(6),
    "duration_sec" DOUBLE PRECISION,
    "moving_duration_sec" DOUBLE PRECISION,
    "elapsed_duration_sec" DOUBLE PRECISION,
    "timezone_offset_min" INTEGER,
    "distance_m" DOUBLE PRECISION,
    "avg_hr" DOUBLE PRECISION,
    "max_hr" DOUBLE PRECISION,
    "avg_speed" DOUBLE PRECISION,
    "calories" DOUBLE PRECISION,
    "aerobic_effect" DOUBLE PRECISION,
    "anaerobic_effect" DOUBLE PRECISION,
    "training_effect_label" TEXT,
    "garmin_activity_load" DOUBLE PRECISION,
    "hr_zone_1_sec" DOUBLE PRECISION,
    "hr_zone_2_sec" DOUBLE PRECISION,
    "hr_zone_3_sec" DOUBLE PRECISION,
    "hr_zone_4_sec" DOUBLE PRECISION,
    "hr_zone_5_sec" DOUBLE PRECISION,
    "source" TEXT NOT NULL DEFAULT 'garmin',
    "source_format" TEXT NOT NULL,
    "source_path" TEXT NOT NULL,
    "source_sha256" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "activity_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "running_activity" (
    "activity_id" BIGINT NOT NULL,
    "avg_cadence_spm" DOUBLE PRECISION,
    "elevation_gain_m" DOUBLE PRECISION,
    "avg_ground_contact_time_ms" DOUBLE PRECISION,
    "avg_vertical_oscillation_cm" DOUBLE PRECISION,
    "avg_stride_length_cm" DOUBLE PRECISION,

    CONSTRAINT "running_activity_pkey" PRIMARY KEY ("activity_id")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "activity_sample" (
    "activity_id" BIGINT NOT NULL,
    "timestamp" TIMESTAMPTZ(6) NOT NULL,
    "metric" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "unit" TEXT,

    CONSTRAINT "activity_sample_pkey" PRIMARY KEY ("activity_id","timestamp","metric")
);

-- CreateTable
CREATE TABLE IF NOT EXISTS "daily_metrics" (
    "date" DATE NOT NULL,
    "resting_hr" DOUBLE PRECISION,
    "overnight_hrv" DOUBLE PRECISION,
    "hrv_status" TEXT,
    "sleep_duration_sec" DOUBLE PRECISION,
    "sleep_score" DOUBLE PRECISION,
    "readiness_score" DOUBLE PRECISION,
    "readiness_level" TEXT,
    "training_status" TEXT,
    "vo2max_generic" DOUBLE PRECISION,
    "vo2max_cycling" DOUBLE PRECISION,
    "garmin_load_acute" DOUBLE PRECISION,
    "garmin_load_chronic" DOUBLE PRECISION,
    "garmin_acwr" DOUBLE PRECISION,
    "monthly_load_aerobic_low" DOUBLE PRECISION,
    "monthly_load_aerobic_high" DOUBLE PRECISION,
    "monthly_load_anaerobic" DOUBLE PRECISION,
    "running_impact_load" DOUBLE PRECISION,
    "running_tolerance" DOUBLE PRECISION,
    "source_format" TEXT NOT NULL,
    "source_path" TEXT NOT NULL,
    "source_sha256" TEXT NOT NULL,

    CONSTRAINT "daily_metrics_pkey" PRIMARY KEY ("date")
);

-- CreateIndex
CREATE UNIQUE INDEX IF NOT EXISTS "activity_garmin_activity_id_key" ON "activity"("garmin_activity_id");

-- AddForeignKey
DO $$
BEGIN
    ALTER TABLE "running_activity"
        ADD CONSTRAINT "running_activity_activity_id_fkey"
        FOREIGN KEY ("activity_id") REFERENCES "activity"("id")
        ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- AddForeignKey
DO $$
BEGIN
    ALTER TABLE "activity_sample"
        ADD CONSTRAINT "activity_sample_activity_id_fkey"
        FOREIGN KEY ("activity_id") REFERENCES "activity"("id")
        ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
