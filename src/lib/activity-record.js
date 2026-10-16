import { formatDuration } from './format.js';

const ACTIVITY_FACTS = [
  ['durationSec', 'Duration', 'duration'],
  ['movingDurationSec', 'Moving time', 'duration'],
  ['elapsedDurationSec', 'Elapsed time', 'duration'],
  ['distanceM', 'Distance', 'distance'],
  ['avgHr', 'Average heart rate', 'bpm'],
  ['maxHr', 'Max heart rate', 'bpm'],
  ['avgSpeed', 'Average speed', 'speed'],
  ['calories', 'Calories', 'kcal'],
  ['aerobicEffect', 'Aerobic effect', 'number'],
  ['anaerobicEffect', 'Anaerobic effect', 'number'],
  ['trainingEffectLabel', 'Training effect', 'text'],
  ['garminActivityLoad', 'Activity load', 'number'],
  ['hrZone1Sec', 'Heart-rate zone 1', 'duration'],
  ['hrZone2Sec', 'Heart-rate zone 2', 'duration'],
  ['hrZone3Sec', 'Heart-rate zone 3', 'duration'],
  ['hrZone4Sec', 'Heart-rate zone 4', 'duration'],
  ['hrZone5Sec', 'Heart-rate zone 5', 'duration'],
  ['totalSets', 'Sets', 'number'],
  ['volumeKg', 'Volume', 'kg'],
  ['estSweatLossMl', 'Sweat loss', 'ml'],
  ['primaryBenefit', 'Primary benefit', 'text'],
  ['recoveryHeartRate', 'Recovery heart rate', 'bpm'],
];

const CYCLING_FACTS = [
  ['avgPowerW', 'Average power', 'watts'],
  ['maxPowerW', 'Max power', 'watts'],
  ['normalizedPowerW', 'Normalized power', 'watts'],
  ['intensityFactor', 'Intensity factor', 'number'],
  ['tss', 'TSS', 'number'],
  ['avgCadenceRpm', 'Average cadence', 'rpm'],
  ['maxCadenceRpm', 'Max cadence', 'rpm'],
  ['totalWorkJ', 'Work', 'kj'],
  ['thresholdPowerW', 'Threshold power', 'watts'],
  ['leftPowerPct', 'Left power', 'percent'],
  ['avgLeftTorqueEffectiveness', 'Left torque effectiveness', 'number'],
  ['avgRightTorqueEffectiveness', 'Right torque effectiveness', 'number'],
  ['avgLeftPedalSmoothness', 'Left pedal smoothness', 'number'],
  ['avgRightPedalSmoothness', 'Right pedal smoothness', 'number'],
  ['avgCombinedPedalSmoothness', 'Pedal smoothness', 'number'],
  ['totalAscentM', 'Ascent', 'meters'],
  ['totalDescentM', 'Descent', 'meters'],
  ['powerZone1Sec', 'Power zone 1', 'duration'],
  ['powerZone2Sec', 'Power zone 2', 'duration'],
  ['powerZone3Sec', 'Power zone 3', 'duration'],
  ['powerZone4Sec', 'Power zone 4', 'duration'],
  ['powerZone5Sec', 'Power zone 5', 'duration'],
  ['powerZone6Sec', 'Power zone 6', 'duration'],
  ['powerZone7Sec', 'Power zone 7', 'duration'],
];

const RUNNING_FACTS = [
  ['avgCadenceSpm', 'Average cadence', 'spm'],
  ['maxCadenceSpm', 'Max cadence', 'spm'],
  ['avgStrideLengthCm', 'Stride length', 'cm'],
  ['elevationGainM', 'Elevation gain', 'meters'],
  ['totalDescentM', 'Descent', 'meters'],
  ['avgGroundContactTimeMs', 'Ground contact time', 'ms'],
  ['avgVerticalOscillationCm', 'Vertical oscillation', 'cm'],
  ['avgVerticalRatio', 'Vertical ratio', 'number'],
  ['avgStanceTimePercent', 'Stance time', 'percent'],
  ['avgStanceTimeBalance', 'Stance balance', 'number'],
  ['avgPowerW', 'Average power', 'watts'],
  ['maxPowerW', 'Max power', 'watts'],
  ['normalizedPowerW', 'Normalized power', 'watts'],
  ['avgRespiration', 'Respiration', 'number'],
  ['maxRespiration', 'Max respiration', 'number'],
  ['totalStrides', 'Strides', 'number'],
];

export function describeActivity(record) {
  const facts = [];
  push(facts, 'When', record?.when);
  push(facts, 'Garmin name', record?.garminName);
  if (record?.parsed) {
    push(facts, 'Sport', sportText(record.sport, record.subSport));
    appendFacts(facts, record, ACTIVITY_FACTS);
    appendFacts(facts, record?.cycling, CYCLING_FACTS);
    appendFacts(facts, record?.running, RUNNING_FACTS);
  }
  return {
    facts,
    sets: Array.isArray(record?.sets) ? record.sets.map(strengthSetLine).filter(Boolean) : [],
  };
}

export function strengthSetLine(set) {
  const name = text(set?.exercise) || text(set?.category);
  const parts = [];
  if (name) parts.push(name);
  const reps = finite(set?.repetitions);
  if (reps != null) parts.push(`${trimNumber(reps)} reps`);
  const weight = finite(set?.weightKg);
  if (weight != null) parts.push(`${trimNumber(weight)} kg`);
  const duration = finite(set?.durationSec);
  if (duration != null) parts.push(formatDuration(duration));
  const kind = text(set?.setType);
  if (kind && kind !== 'active' && kind !== name) parts.push(kind);
  return parts.join(' · ');
}

function appendFacts(facts, source, fields) {
  if (source == null) return;
  for (const [key, label, kind] of fields) {
    push(facts, label, formatFact(source[key], kind));
  }
}

function formatFact(value, kind) {
  if (kind === 'text') return text(value);
  if (kind === 'duration') {
    const seconds = finite(value);
    if (seconds == null) return null;
    const shown = formatDuration(seconds);
    return shown === '—' ? null : shown;
  }
  if (kind === 'distance') {
    const meters = finite(value);
    return meters == null ? null : `${(meters / 1000).toFixed(2)} km`;
  }
  if (kind === 'speed') {
    const metersPerSecond = finite(value);
    return metersPerSecond == null ? null : `${trimNumber(metersPerSecond * 3.6)} km/h`;
  }
  const number = finite(value);
  if (number == null) return null;
  const shown = trimNumber(number);
  if (kind === 'bpm') return `${shown} bpm`;
  if (kind === 'kcal') return `${shown} kcal`;
  if (kind === 'watts') return `${shown} W`;
  if (kind === 'rpm') return `${shown} rpm`;
  if (kind === 'spm') return `${shown} spm`;
  if (kind === 'kg') return `${shown} kg`;
  if (kind === 'ml') return `${shown} ml`;
  if (kind === 'kj') return `${trimNumber(number / 1000)} kJ`;
  if (kind === 'percent') return `${shown}%`;
  if (kind === 'meters') return `${shown} m`;
  if (kind === 'cm') return `${shown} cm`;
  if (kind === 'ms') return `${shown} ms`;
  return shown;
}

function sportText(sport, subSport) {
  const main = text(sport);
  const sub = text(subSport);
  if (!main) return sub;
  if (!sub || sub === 'generic') return main;
  return `${main} / ${sub}`;
}

function push(facts, label, value) {
  if (value == null || value === '') return;
  facts.push({ label, value });
}

function text(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed || null;
}

function finite(value) {
  if (value == null || value === '') return null;
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}

function trimNumber(value) {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}
