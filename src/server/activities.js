import { formatActivity } from '@/lib/format';
import { getPrisma } from '@/server/db';

export async function listActivities() {
  const prisma = getPrisma();
  const rows = await prisma.$queryRaw`
    SELECT
      raw.garmin_activity_id::text AS garmin_activity_id,
      activity.start_at,
      activity.timezone_offset_min,
      activity.sport,
      activity.sub_sport,
      activity.duration_sec,
      activity.distance_m,
      (activity.id IS NOT NULL) AS parsed
    FROM (
      SELECT DISTINCT ON (garmin_activity_id)
        garmin_activity_id,
        created_at,
        id
      FROM raw_object
      WHERE kind = 'activity' AND garmin_activity_id IS NOT NULL
      ORDER BY garmin_activity_id, created_at DESC, id DESC
    ) raw
    LEFT JOIN activity ON activity.garmin_activity_id = raw.garmin_activity_id
    ORDER BY COALESCE(activity.start_at, raw.created_at) DESC
  `;
  return rows.map((row) => formatActivity(row));
}
