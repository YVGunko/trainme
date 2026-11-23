// Why a FIT file cannot be sent as a workout, and what about it was not kept.
// Each sentence names what the file actually is, because the user picked it by
// hand and needs to know whether to look for a different file or fix this one.
//
// Garmin Connect imports FIT activity files only. It has no workout import,
// so a FIT workout reaches Garmin as workout JSON, not as a file.
export const FIT_REASONS = {
  activity_file:
    'This is an activity file, not a workout. Garmin Connect does not import FIT workouts, only activities.',
  other_file: 'This FIT file is another type, not a workout.',
  no_workout_message: 'The file has no workout message.',
  unreadable: 'The file is damaged or it is not a FIT file.',
  empty: 'The file is empty.',
  too_large: 'The file is larger than 256 KB.',
  missing: 'No file was attached.',
  bad_base64: 'The file could not be read.',
};

export function fitReason(reason) {
  return FIT_REASONS[reason] || '';
}

function seconds(value) {
  const rounded = Math.round(Number(value) * 10) / 10;
  return `${rounded} s`;
}

function meters(value) {
  const rounded = Math.round(Number(value) * 10) / 10;
  return `${rounded} m`;
}

// The server reports warnings as codes plus the values behind them, so the
// sentence lives here.
const WARNING_SENTENCES = {
  step_names_dropped: (w) => `Step names are not carried over (${w.count}).`,
  notes_dropped: (w) => `Step notes are not carried over (${w.count}).`,
  short_steps: (w) =>
    `The file looks as if its time units are wrong: ${w.count} step(s) are shorter than a second, the shortest ${seconds(w.smallest)}. Garmin would accept this as a workout of a few seconds. Check the file.`,
  short_distance_steps: (w) =>
    `The file looks as if its distance units are wrong: ${w.count} step(s) are shorter than a metre, the shortest ${meters(w.smallest)}.`,
  short_workout: (w) =>
    `The whole workout lasts ${seconds(w.total_seconds)}. For a planned workout that is almost certainly an error in the file.`,
};

export function warningText(warning) {
  if (!warning || typeof warning.code !== 'string') return '';
  const render = WARNING_SENTENCES[warning.code];
  return render ? render(warning) : '';
}

// Warnings that mean the numbers themselves are suspect, not just lost text.
const NUMERIC_CODES = new Set(['short_steps', 'short_distance_steps', 'short_workout']);

export function hasNumericWarning(warnings) {
  return Array.isArray(warnings) && warnings.some((warning) => NUMERIC_CODES.has(warning?.code));
}

export function warningTexts(warnings) {
  if (!Array.isArray(warnings)) return [];
  return warnings.map(warningText).filter(Boolean);
}
