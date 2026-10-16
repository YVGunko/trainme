import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { CREATE_SUBJECTIVE_LOG } from '../src/lib/subjective-log-sql.js';
import {
  formatMetricNumber,
  formatSleep,
  garminLines,
  isBlankWellness,
  localCalendarDate,
  parseCalendarDate,
  parseWellness,
  presentGarmin,
  presentWellness,
  SCORE_FIELDS,
  SCORE_WORDS,
} from '../src/lib/wellness.js';

test('score words run from best to worst', () => {
  assert.deepEqual(SCORE_WORDS.fatigue, ['None', 'Low', 'Average', 'High']);
  assert.deepEqual(SCORE_WORDS.soreness, SCORE_WORDS.fatigue);
  assert.deepEqual(SCORE_WORDS.stress, SCORE_WORDS.fatigue);
  assert.deepEqual(SCORE_WORDS.injury, SCORE_WORDS.fatigue);
  assert.deepEqual(SCORE_WORDS.illness, SCORE_WORDS.fatigue);
  assert.deepEqual(SCORE_WORDS.sleep_quality, ['Excellent', 'Good', 'Average', 'Poor']);
  assert.deepEqual(SCORE_WORDS.mood, SCORE_WORDS.sleep_quality);
  assert.deepEqual(SCORE_WORDS.motivation, ['High', 'Normal', 'Low', 'Very low']);
});

test('a calendar date is the browser local day', () => {
  assert.equal(localCalendarDate(new Date(2026, 9, 16, 23, 30)), '2026-10-16');
  assert.equal(localCalendarDate(new Date(2026, 0, 5, 0, 30)), '2026-01-05');
});

test('calendar dates reject impossible days', () => {
  assert.equal(parseCalendarDate('2026-10-16'), '2026-10-16');
  assert.throws(() => parseCalendarDate('2026-02-31'), /YYYY-MM-DD/);
  assert.throws(() => parseCalendarDate('2026-10-16T00:00:00'), /YYYY-MM-DD/);
  assert.throws(() => parseCalendarDate(20261016), /YYYY-MM-DD/);
});

test('wellness scores are empty or integers 1 through 4', () => {
  const row = parseWellness({
    fatigue: 1,
    soreness: '',
    mood: null,
    motivation: 4,
    stress: 2,
    sleep_quality: 3,
    injury: 1,
    illness: 4,
    note: '  rest day  ',
    pain: 3,
    rpe: 8,
  });
  assert.equal(row.fatigue, 1);
  assert.equal(row.soreness, null);
  assert.equal(row.mood, null);
  assert.equal(row.motivation, 4);
  assert.equal(row.note, 'rest day');
  assert.equal('pain' in row, false);
  assert.equal('rpe' in row, false);
  assert.equal(isBlankWellness(row), false);

  for (const value of [0, 5, 1.5, true, '1']) {
    assert.throws(() => parseWellness({ fatigue: value }), /Fatigue must be 1, 2, 3, or 4/);
  }
  assert.throws(() => parseWellness({ note: 12 }), /Note must be text/);
  assert.throws(() => parseWellness({ note: 'x'.repeat(4001) }), /Note is too long/);
  assert.equal(parseWellness({ note: 'x'.repeat(4000) }).note.length, 4000);
  assert.equal(parseWellness({ note: '   ' }).note, null);
  assert.equal(isBlankWellness(parseWellness({})), true);
  assert.throws(() => parseWellness(['fatigue']), /Could not save/);
});

test('sleep is shown in hours and minutes and empty garmin fields stay hidden', () => {
  assert.equal(formatSleep(25000), '6h 57m');
  assert.equal(formatSleep(3600), '1h 0m');
  assert.equal(formatSleep(0), '0h 0m');
  assert.equal(formatSleep(-1), null);
  assert.equal(formatMetricNumber(80), '80');
  assert.equal(formatMetricNumber(54.4), '54.4');
  assert.equal(formatMetricNumber(0.9), '0.9');
  assert.equal(formatMetricNumber(967.12445), '967.12445');

  const lines = garminLines({
    sleep_duration_sec: 25000,
    sleep_score: null,
    hrv_status: 'UNBALANCED',
    running_tolerance: 12,
    running_impact_load: 4,
  });
  assert.deepEqual(lines, [
    { key: 'sleep_duration_sec', label: 'Sleep', value: '6h 57m' },
    { key: 'hrv_status', label: 'HRV status', value: 'UNBALANCED' },
  ]);
  assert.deepEqual(presentGarmin({ sleep_score: '80', hrv_status: '  ', resting_hr: null }), {
    sleep_score: 80,
  });
  assert.deepEqual(presentWellness({ fatigue: '2', note: '', soreness: 9 }), {
    fatigue: 2,
    soreness: null,
    mood: null,
    motivation: null,
    stress: null,
    sleep_quality: null,
    injury: null,
    illness: null,
    note: null,
  });
  assert.equal(SCORE_FIELDS.length, 8);
});

test('the wellness table migration matches the statement the app runs', () => {
  const file = readFileSync(
    new URL('../prisma/migrations/20261016140000_subjective_log/migration.sql', import.meta.url),
    'utf8'
  );
  assert.equal(file.trim(), CREATE_SUBJECTIVE_LOG.trim());
  assert.equal(file.includes('daily_metrics'), false);
});
