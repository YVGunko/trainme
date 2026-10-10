import assert from 'node:assert/strict';
import test from 'node:test';
import { formatActivity } from '../src/lib/format.js';

test('formats a parsed run in the stored local offset', () => {
  const row = formatActivity({
    garmin_activity_id: '24675004034',
    start_at: new Date('2026-10-10T04:21:00.000Z'),
    timezone_offset_min: 180,
    sport: 'running',
    sub_sport: 'generic',
    duration_sec: 3526,
    distance_m: 11504,
    parsed: true,
  });

  assert.deepEqual(row, {
    garminActivityId: '24675004034',
    when: '2026-10-10 07:21',
    sport: 'running',
    duration: '58:46',
    distance: '11.50 км',
    parsed: true,
  });
});

test('keeps an uploaded file visible before it is parsed', () => {
  const row = formatActivity({
    garmin_activity_id: 24637463621,
    start_at: null,
    timezone_offset_min: null,
    sport: null,
    sub_sport: null,
    duration_sec: null,
    distance_m: null,
    parsed: false,
  });

  assert.equal(row.when, '—');
  assert.equal(row.sport, '—');
  assert.equal(row.duration, '—');
  assert.equal(row.distance, '—');
  assert.equal(row.parsed, false);
});

test('shows cycling subtype and a zero distance', () => {
  const row = formatActivity({
    garmin_activity_id: '1',
    start_at: new Date('2026-10-07T15:47:45.000Z'),
    timezone_offset_min: 180,
    sport: 'cycling',
    sub_sport: 'indoor_cycling',
    duration_sec: 3841,
    distance_m: 0,
    parsed: true,
  });

  assert.equal(row.when, '2026-10-07 18:47');
  assert.equal(row.sport, 'cycling / indoor_cycling');
  assert.equal(row.duration, '1:04:01');
  assert.equal(row.distance, '0.00 км');
});
