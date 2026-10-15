import { getPrisma } from '@/server/db';

const CREATE_ACTIVITY_META = `
CREATE TABLE IF NOT EXISTS activity_meta (
    garmin_activity_id bigint PRIMARY KEY,
    garmin_name text,
    title text,
    description text,
    start_local timestamp without time zone,
    hr_zone_1_sec double precision,
    hr_zone_2_sec double precision,
    hr_zone_3_sec double precision,
    hr_zone_4_sec double precision,
    hr_zone_5_sec double precision,
    power_zone_1_sec double precision,
    power_zone_2_sec double precision,
    power_zone_3_sec double precision,
    power_zone_4_sec double precision,
    power_zone_5_sec double precision,
    power_zone_6_sec double precision,
    power_zone_7_sec double precision,
    updated_at timestamptz NOT NULL DEFAULT now()
)`;

const ADD_HR_ZONE_SECONDS = [1, 2, 3, 4, 5].map(
  (zone) =>
    `ALTER TABLE activity_meta ADD COLUMN IF NOT EXISTS hr_zone_${zone}_sec double precision`
);

const ADD_POWER_ZONE_SECONDS = [1, 2, 3, 4, 5, 6, 7].map(
  (zone) =>
    `ALTER TABLE activity_meta ADD COLUMN IF NOT EXISTS power_zone_${zone}_sec double precision`
);

export async function ensureActivityMeta() {
  const prisma = getPrisma();
  await prisma.$executeRawUnsafe(CREATE_ACTIVITY_META);
  for (const statement of ADD_HR_ZONE_SECONDS) {
    await prisma.$executeRawUnsafe(statement);
  }
  for (const statement of ADD_POWER_ZONE_SECONDS) {
    await prisma.$executeRawUnsafe(statement);
  }
  return prisma;
}

export async function saveActivityNote(garminActivityId, title, description) {
  const prisma = await ensureActivityMeta();
  await prisma.$executeRaw`
    INSERT INTO activity_meta (garmin_activity_id, title, description)
    VALUES (${BigInt(garminActivityId)}, ${title}, ${description})
    ON CONFLICT (garmin_activity_id) DO UPDATE
    SET title = EXCLUDED.title,
        description = EXCLUDED.description,
        updated_at = now()
  `;
}
