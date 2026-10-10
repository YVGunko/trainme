import { getPrisma } from '@/server/db';

const CREATE_ACTIVITY_META = `
CREATE TABLE IF NOT EXISTS activity_meta (
    garmin_activity_id bigint PRIMARY KEY,
    garmin_name text,
    title text,
    description text,
    start_local timestamp without time zone,
    updated_at timestamptz NOT NULL DEFAULT now()
)`;

export async function ensureActivityMeta() {
  const prisma = getPrisma();
  await prisma.$executeRawUnsafe(CREATE_ACTIVITY_META);
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
