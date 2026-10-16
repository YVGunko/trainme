export const SCORE_FIELDS = [
  'fatigue',
  'soreness',
  'mood',
  'motivation',
  'stress',
  'sleep_quality',
  'injury',
  'illness',
];

export const SCORE_LABELS = {
  fatigue: 'Fatigue',
  soreness: 'Soreness',
  mood: 'Mood',
  motivation: 'Motivation',
  stress: 'Stress',
  sleep_quality: 'Sleep quality',
  injury: 'Injury',
  illness: 'Illness',
};

// 1 is the best step and 4 is the worst step. The database stores the number.
export const SCORE_WORDS = {
  fatigue: ['None', 'Low', 'Average', 'High'],
  soreness: ['None', 'Low', 'Average', 'High'],
  stress: ['None', 'Low', 'Average', 'High'],
  injury: ['None', 'Low', 'Average', 'High'],
  illness: ['None', 'Low', 'Average', 'High'],
  sleep_quality: ['Excellent', 'Good', 'Average', 'Poor'],
  mood: ['Excellent', 'Good', 'Average', 'Poor'],
  motivation: ['High', 'Normal', 'Low', 'Very low'],
};

export const GARMIN_FIELDS = [
  { key: 'sleep_duration_sec', label: 'Sleep', kind: 'duration' },
  { key: 'sleep_score', label: 'Sleep score', kind: 'number' },
  { key: 'overnight_hrv', label: 'Overnight HRV', kind: 'number' },
  { key: 'resting_hr', label: 'Resting heart rate', kind: 'number' },
  { key: 'hrv_status', label: 'HRV status', kind: 'text' },
  { key: 'readiness_score', label: 'Readiness', kind: 'number' },
  { key: 'readiness_level', label: 'Readiness level', kind: 'text' },
  { key: 'training_status', label: 'Training status', kind: 'text' },
  { key: 'garmin_load_acute', label: 'Acute load', kind: 'number' },
  { key: 'garmin_load_chronic', label: 'Chronic load', kind: 'number' },
  { key: 'garmin_acwr', label: 'Garmin ACWR', kind: 'number' },
  { key: 'vo2max_generic', label: 'VO2max', kind: 'number' },
  { key: 'vo2max_cycling', label: 'Cycling VO2max', kind: 'number' },
  { key: 'monthly_load_aerobic_low', label: 'Low aerobic load', kind: 'number' },
  { key: 'monthly_load_aerobic_high', label: 'High aerobic load', kind: 'number' },
  { key: 'monthly_load_anaerobic', label: 'Anaerobic load', kind: 'number' },
];

const NOTE_LIMIT = 4000;

export function localCalendarDate(now = new Date()) {
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

export function parseCalendarDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    invalid('Date must be YYYY-MM-DD.');
  }
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    invalid('Date must be YYYY-MM-DD.');
  }
  return value;
}

export function parseWellness(body) {
  if (body == null || typeof body !== 'object' || Array.isArray(body)) {
    invalid('Could not save.');
  }
  const row = {};
  for (const field of SCORE_FIELDS) {
    row[field] = parseScore(field, body[field]);
  }
  row.note = parseNote(body.note);
  return row;
}

export function isBlankWellness(row) {
  return SCORE_FIELDS.every((field) => row[field] == null) && row.note == null;
}

export function dayNeedsCheckIn(wellness) {
  if (wellness == null) return true;
  return isBlankWellness(wellness);
}

export function emptyWellnessForm() {
  const form = { note: '' };
  for (const field of SCORE_FIELDS) form[field] = null;
  return form;
}

export function formFromWellness(row) {
  const form = emptyWellnessForm();
  if (row == null) return form;
  for (const field of SCORE_FIELDS) {
    form[field] = row[field] == null ? null : row[field];
  }
  form.note = row.note || '';
  return form;
}

export function formatSleep(seconds) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return null;
  const minutesTotal = Math.round(seconds / 60);
  const hours = Math.floor(minutesTotal / 60);
  const minutes = minutesTotal % 60;
  return `${hours}h ${minutes}m`;
}

export function formatMetricNumber(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const rounded = Math.round(value * 1e6) / 1e6;
  if (Object.is(rounded, -0)) return '0';
  return String(rounded);
}

export function garminLines(row) {
  if (row == null || typeof row !== 'object') return [];
  const lines = [];
  for (const field of GARMIN_FIELDS) {
    const value = coerceGarmin(field, row[field.key]);
    if (value == null) continue;
    const text = field.kind === 'duration' ? formatSleep(value) : field.kind === 'number' ? formatMetricNumber(value) : value;
    if (text == null || text === '') continue;
    lines.push({ key: field.key, label: field.label, value: text });
  }
  return lines;
}

export function presentGarmin(row) {
  const present = {};
  if (row == null || typeof row !== 'object') return present;
  for (const field of GARMIN_FIELDS) {
    const value = coerceGarmin(field, row[field.key]);
    if (value != null) present[field.key] = value;
  }
  return present;
}

export function presentWellness(row) {
  const present = {};
  for (const field of SCORE_FIELDS) {
    const value = row?.[field];
    const number = value == null ? null : Number(value);
    present[field] = Number.isInteger(number) && number >= 1 && number <= 4 ? number : null;
  }
  present.note = typeof row?.note === 'string' && row.note ? row.note : null;
  return present;
}

function coerceGarmin(field, value) {
  if (value == null || value === '') return null;
  if (field.kind === 'text') {
    return typeof value === 'string' && value.trim() ? value : null;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  if (typeof value === 'object' && value != null && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function parseScore(field, value) {
  if (value == null || value === '') return null;
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 1 || value > 4) {
    invalid(`${SCORE_LABELS[field]} must be 1, 2, 3, or 4.`);
  }
  return value;
}

function parseNote(value) {
  if (value == null) return null;
  if (typeof value !== 'string') invalid('Note must be text.');
  const text = value.trim();
  if (!text) return null;
  if (text.length > NOTE_LIMIT) invalid('Note is too long.');
  return text;
}

function invalid(message) {
  const error = new Error(message);
  error.status = 400;
  error.publicMessage = message;
  throw error;
}
