import { CREATE_SUBJECTIVE_LOG } from '@/lib/subjective-log-sql';
import { isBlankWellness, presentGarmin, presentWellness } from '@/lib/wellness';
import { getPrisma } from '@/server/db';

export async function ensureSubjectiveLog() {
  const prisma = getPrisma();
  await prisma.$executeRawUnsafe(CREATE_SUBJECTIVE_LOG);
  return prisma;
}

export async function readDay(date) {
  const prisma = await ensureSubjectiveLog();
  const garminRows = await prisma.$queryRaw`
    SELECT
      resting_hr,
      overnight_hrv,
      hrv_status,
      sleep_duration_sec,
      sleep_score,
      readiness_score,
      readiness_level,
      training_status,
      vo2max_generic,
      vo2max_cycling,
      garmin_load_acute,
      garmin_load_chronic,
      garmin_acwr,
      monthly_load_aerobic_low,
      monthly_load_aerobic_high,
      monthly_load_anaerobic
    FROM daily_metrics
    WHERE date = CAST(${date} AS date)
  `;
  const wellnessRows = await prisma.$queryRaw`
    SELECT fatigue, soreness, mood, motivation, stress, sleep_quality, injury, illness, note
    FROM subjective_log
    WHERE date = CAST(${date} AS date)
  `;
  return {
    date,
    garmin: garminRows.length ? presentGarmin(garminRows[0]) : null,
    wellness: wellnessRows.length ? presentWellness(wellnessRows[0]) : null,
  };
}

export async function saveWellness(date, row) {
  const prisma = await ensureSubjectiveLog();
  if (isBlankWellness(row)) {
    await prisma.$executeRaw`
      DELETE FROM subjective_log
      WHERE date = CAST(${date} AS date)
    `;
    return readDay(date);
  }
  await prisma.$executeRaw`
    INSERT INTO subjective_log (
      date,
      fatigue,
      soreness,
      mood,
      motivation,
      stress,
      sleep_quality,
      injury,
      illness,
      note,
      updated_at
    )
    VALUES (
      CAST(${date} AS date),
      ${row.fatigue},
      ${row.soreness},
      ${row.mood},
      ${row.motivation},
      ${row.stress},
      ${row.sleep_quality},
      ${row.injury},
      ${row.illness},
      ${row.note},
      now()
    )
    ON CONFLICT (date) DO UPDATE
    SET fatigue = EXCLUDED.fatigue,
        soreness = EXCLUDED.soreness,
        mood = EXCLUDED.mood,
        motivation = EXCLUDED.motivation,
        stress = EXCLUDED.stress,
        sleep_quality = EXCLUDED.sleep_quality,
        injury = EXCLUDED.injury,
        illness = EXCLUDED.illness,
        note = EXCLUDED.note,
        updated_at = now()
  `;
  return readDay(date);
}
