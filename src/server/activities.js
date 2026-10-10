import { formatActivity } from '@/lib/format';
import { ensureActivityMeta } from '@/server/meta';

export async function listActivities() {
  const prisma = await ensureActivityMeta();
  const rows = await prisma.$queryRaw`
    SELECT
      raw.garmin_activity_id::text AS garmin_activity_id,
      meta.garmin_name,
      meta.title,
      meta.description,
      to_char(meta.start_local, 'YYYY-MM-DD HH24:MI:SS') AS start_local,
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
    LEFT JOIN activity_meta meta ON meta.garmin_activity_id = raw.garmin_activity_id
    LEFT JOIN activity ON activity.garmin_activity_id = raw.garmin_activity_id
    ORDER BY meta.start_local DESC NULLS LAST, activity.start_at DESC NULLS LAST
  `;
  return rows.map((row) => formatActivity(row));
}
