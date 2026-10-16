import { ensureActivityMeta } from '@/server/meta';

export async function readActivityRecord(garminActivityId) {
  const prisma = await ensureActivityMeta();
  const id = BigInt(garminActivityId);
  const rows = await prisma.$queryRaw`
    SELECT
      meta.garmin_name,
      meta.title,
      meta.description,
      to_char(meta.start_local, 'YYYY-MM-DD HH24:MI:SS') AS start_local,
      (activity.id IS NOT NULL) AS parsed,
      activity.sport,
      activity.sub_sport,
      activity.duration_sec,
      activity.moving_duration_sec,
      activity.elapsed_duration_sec,
      activity.distance_m,
      activity.avg_hr,
      activity.max_hr,
      activity.avg_speed,
      activity.calories,
      activity.aerobic_effect,
      activity.anaerobic_effect,
      activity.training_effect_label,
      activity.garmin_activity_load,
      activity.hr_zone_1_sec,
      activity.hr_zone_2_sec,
      activity.hr_zone_3_sec,
      activity.hr_zone_4_sec,
      activity.hr_zone_5_sec,
      activity.total_sets,
      activity.volume_kg,
      activity.est_sweat_loss_ml,
      activity.primary_benefit,
      activity.recovery_heart_rate,
      cycling.avg_power_w AS cycling_avg_power_w,
      cycling.max_power_w AS cycling_max_power_w,
      cycling.normalized_power_w AS cycling_normalized_power_w,
      cycling.intensity_factor AS cycling_intensity_factor,
      cycling.tss AS cycling_tss,
      cycling.avg_cadence_rpm AS cycling_avg_cadence_rpm,
      cycling.max_cadence_rpm AS cycling_max_cadence_rpm,
      cycling.total_work_j AS cycling_total_work_j,
      cycling.threshold_power_w AS cycling_threshold_power_w,
      cycling.left_power_pct AS cycling_left_power_pct,
      cycling.avg_left_torque_effectiveness AS cycling_left_torque,
      cycling.avg_right_torque_effectiveness AS cycling_right_torque,
      cycling.avg_left_pedal_smoothness AS cycling_left_smoothness,
      cycling.avg_right_pedal_smoothness AS cycling_right_smoothness,
      cycling.avg_combined_pedal_smoothness AS cycling_combined_smoothness,
      cycling.total_ascent_m AS cycling_total_ascent_m,
      cycling.total_descent_m AS cycling_total_descent_m,
      cycling.power_zone_1_sec AS cycling_power_zone_1_sec,
      cycling.power_zone_2_sec AS cycling_power_zone_2_sec,
      cycling.power_zone_3_sec AS cycling_power_zone_3_sec,
      cycling.power_zone_4_sec AS cycling_power_zone_4_sec,
      cycling.power_zone_5_sec AS cycling_power_zone_5_sec,
      cycling.power_zone_6_sec AS cycling_power_zone_6_sec,
      cycling.power_zone_7_sec AS cycling_power_zone_7_sec,
      running.avg_cadence_spm AS running_avg_cadence_spm,
      running.max_cadence_spm AS running_max_cadence_spm,
      running.avg_stride_length_cm AS running_avg_stride_length_cm,
      running.elevation_gain_m AS running_elevation_gain_m,
      running.total_descent_m AS running_total_descent_m,
      running.avg_ground_contact_time_ms AS running_ground_contact_ms,
      running.avg_vertical_oscillation_cm AS running_vertical_oscillation_cm,
      running.avg_vertical_ratio AS running_vertical_ratio,
      running.avg_stance_time_percent AS running_stance_time_percent,
      running.avg_stance_time_balance AS running_stance_balance,
      running.avg_power_w AS running_avg_power_w,
      running.max_power_w AS running_max_power_w,
      running.normalized_power_w AS running_normalized_power_w,
      running.avg_respiration AS running_avg_respiration,
      running.max_respiration AS running_max_respiration,
      running.total_strides AS running_total_strides
    FROM raw_object
    LEFT JOIN activity_meta meta ON meta.garmin_activity_id = raw_object.garmin_activity_id
    LEFT JOIN activity ON activity.garmin_activity_id = raw_object.garmin_activity_id
    LEFT JOIN cycling_activity cycling ON cycling.activity_id = activity.id
    LEFT JOIN running_activity running ON running.activity_id = activity.id
    WHERE raw_object.kind = 'activity' AND raw_object.garmin_activity_id = ${id}
    ORDER BY raw_object.created_at DESC, raw_object.id DESC
    LIMIT 1
  `;
  if (!rows.length) return null;
  const sets = await prisma.$queryRaw`
    SELECT
      strength_set.set_index,
      strength_set.set_type,
      strength_set.category,
      strength_set.exercise,
      strength_set.repetitions,
      strength_set.weight_kg,
      strength_set.duration_sec
    FROM strength_set
    JOIN activity ON activity.id = strength_set.activity_id
    WHERE activity.garmin_activity_id = ${id}
    ORDER BY strength_set.set_index
  `;
  return presentRecord(String(garminActivityId), rows[0], sets);
}

function presentRecord(garminActivityId, row, sets) {
  const parsed = Boolean(row.parsed);
  return {
    garminActivityId,
    parsed,
    garminName: text(row.garmin_name),
    title: text(row.title),
    description: text(row.description),
    when: text(row.start_local)?.slice(0, 16) || null,
    sport: parsed ? text(row.sport) : null,
    subSport: parsed ? text(row.sub_sport) : null,
    durationSec: parsed ? number(row.duration_sec) : null,
    movingDurationSec: parsed ? number(row.moving_duration_sec) : null,
    elapsedDurationSec: parsed ? number(row.elapsed_duration_sec) : null,
    distanceM: parsed ? number(row.distance_m) : null,
    avgHr: parsed ? number(row.avg_hr) : null,
    maxHr: parsed ? number(row.max_hr) : null,
    avgSpeed: parsed ? number(row.avg_speed) : null,
    calories: parsed ? number(row.calories) : null,
    aerobicEffect: parsed ? number(row.aerobic_effect) : null,
    anaerobicEffect: parsed ? number(row.anaerobic_effect) : null,
    trainingEffectLabel: parsed ? text(row.training_effect_label) : null,
    garminActivityLoad: parsed ? number(row.garmin_activity_load) : null,
    hrZone1Sec: parsed ? number(row.hr_zone_1_sec) : null,
    hrZone2Sec: parsed ? number(row.hr_zone_2_sec) : null,
    hrZone3Sec: parsed ? number(row.hr_zone_3_sec) : null,
    hrZone4Sec: parsed ? number(row.hr_zone_4_sec) : null,
    hrZone5Sec: parsed ? number(row.hr_zone_5_sec) : null,
    totalSets: parsed ? number(row.total_sets) : null,
    volumeKg: parsed ? number(row.volume_kg) : null,
    estSweatLossMl: parsed ? number(row.est_sweat_loss_ml) : null,
    primaryBenefit: parsed ? text(row.primary_benefit) : null,
    recoveryHeartRate: parsed ? number(row.recovery_heart_rate) : null,
    cycling: parsed ? cyclingBlock(row) : null,
    running: parsed ? runningBlock(row) : null,
    sets: parsed
      ? sets.map((set) => ({
          index: Number(set.set_index),
          setType: text(set.set_type),
          category: text(set.category),
          exercise: text(set.exercise),
          repetitions: number(set.repetitions),
          weightKg: number(set.weight_kg),
          durationSec: number(set.duration_sec),
        }))
      : [],
  };
}

function cyclingBlock(row) {
  const block = {
    avgPowerW: number(row.cycling_avg_power_w),
    maxPowerW: number(row.cycling_max_power_w),
    normalizedPowerW: number(row.cycling_normalized_power_w),
    intensityFactor: number(row.cycling_intensity_factor),
    tss: number(row.cycling_tss),
    avgCadenceRpm: number(row.cycling_avg_cadence_rpm),
    maxCadenceRpm: number(row.cycling_max_cadence_rpm),
    totalWorkJ: number(row.cycling_total_work_j),
    thresholdPowerW: number(row.cycling_threshold_power_w),
    leftPowerPct: number(row.cycling_left_power_pct),
    avgLeftTorqueEffectiveness: number(row.cycling_left_torque),
    avgRightTorqueEffectiveness: number(row.cycling_right_torque),
    avgLeftPedalSmoothness: number(row.cycling_left_smoothness),
    avgRightPedalSmoothness: number(row.cycling_right_smoothness),
    avgCombinedPedalSmoothness: number(row.cycling_combined_smoothness),
    totalAscentM: number(row.cycling_total_ascent_m),
    totalDescentM: number(row.cycling_total_descent_m),
    powerZone1Sec: number(row.cycling_power_zone_1_sec),
    powerZone2Sec: number(row.cycling_power_zone_2_sec),
    powerZone3Sec: number(row.cycling_power_zone_3_sec),
    powerZone4Sec: number(row.cycling_power_zone_4_sec),
    powerZone5Sec: number(row.cycling_power_zone_5_sec),
    powerZone6Sec: number(row.cycling_power_zone_6_sec),
    powerZone7Sec: number(row.cycling_power_zone_7_sec),
  };
  return Object.values(block).some((value) => value != null) ? block : null;
}

function runningBlock(row) {
  const block = {
    avgCadenceSpm: number(row.running_avg_cadence_spm),
    maxCadenceSpm: number(row.running_max_cadence_spm),
    avgStrideLengthCm: number(row.running_avg_stride_length_cm),
    elevationGainM: number(row.running_elevation_gain_m),
    totalDescentM: number(row.running_total_descent_m),
    avgGroundContactTimeMs: number(row.running_ground_contact_ms),
    avgVerticalOscillationCm: number(row.running_vertical_oscillation_cm),
    avgVerticalRatio: number(row.running_vertical_ratio),
    avgStanceTimePercent: number(row.running_stance_time_percent),
    avgStanceTimeBalance: number(row.running_stance_balance),
    avgPowerW: number(row.running_avg_power_w),
    maxPowerW: number(row.running_max_power_w),
    normalizedPowerW: number(row.running_normalized_power_w),
    avgRespiration: number(row.running_avg_respiration),
    maxRespiration: number(row.running_max_respiration),
    totalStrides: number(row.running_total_strides),
  };
  return Object.values(block).some((value) => value != null) ? block : null;
}

function text(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function number(value) {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
