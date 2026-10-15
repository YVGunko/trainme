export const ACTIVITY_NORMALIZE_TOPIC = 'activity-normalize';

export function newActivityIds(result) {
  const activities = Array.isArray(result?.activities) ? result.activities : [];
  const ids = [];
  for (const item of activities) {
    if (!item || item.stored !== true) continue;
    const id = activityId(item.garmin_activity_id);
    if (id !== null) ids.push(id);
  }
  return ids;
}

export async function enqueueActivityParses(result, send) {
  const queued = [];
  const failed = [];
  for (const garminActivityId of newActivityIds(result)) {
    try {
      await send(ACTIVITY_NORMALIZE_TOPIC, { garminActivityId });
      queued.push(garminActivityId);
    } catch {
      failed.push({ garminActivityId });
    }
  }
  return { queued, failed };
}

function activityId(value) {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value;
  if (typeof value === 'string' && /^\d+$/.test(value)) {
    const parsed = Number(value);
    if (Number.isSafeInteger(parsed) && parsed > 0) return parsed;
  }
  return null;
}
