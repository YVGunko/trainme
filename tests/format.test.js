import assert from 'node:assert/strict';
import test from 'node:test';
import { formatActivity } from '../src/lib/format.js';

test('uses the Garmin local start and Garmin name before the sport type', () => {
  const row = formatActivity({
    garmin_activity_id: '24675004034',
    garmin_name: 'Morning run',
    title: '',
    description: 'легко',
    start_local: '2026-10-10 07:21:13',
    start_at: new Date('2026-10-10T04:21:00.000Z'),
    timezone_offset_min: 180,
    sport: 'running',
    sub_sport: 'generic',
    duration_sec: 3526,
    distance_m: 11504,
    parsed: true,
  });

  assert.equal(row.when, '2026-10-10 07:21');
  assert.equal(row.title, 'Morning run');
  assert.equal(row.fallbackTitle, 'Morning run');
  assert.equal(row.description, 'легко');
  assert.equal(row.sport, 'running');
  assert.equal(row.parsed, true);
});

test('keeps a custom title and falls back to the sport when Garmin has no name', () => {
  const custom = formatActivity({
    garmin_activity_id: '1',
    garmin_name: 'Morning run',
    title: 'Моя',
    sport: 'running',
    sub_sport: 'generic',
    parsed: true,
  });
  assert.equal(custom.title, 'Моя');
  assert.equal(custom.customTitle, 'Моя');
  assert.equal(custom.fallbackTitle, 'Morning run');

  const sport = formatActivity({
    garmin_activity_id: '2',
    sport: 'cycling',
    sub_sport: 'indoor_cycling',
    duration_sec: 3841,
    distance_m: 0,
    parsed: true,
    start_at: new Date('2026-10-07T15:47:45.000Z'),
    timezone_offset_min: 180,
  });
  assert.equal(sport.title, 'cycling / indoor_cycling');
  assert.equal(sport.when, '2026-10-07 18:47');
  assert.equal(sport.distance, '0.00 км');
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
  assert.equal(row.title, '—');
  assert.equal(row.sport, '—');
  assert.equal(row.duration, '—');
  assert.equal(row.distance, '—');
  assert.equal(row.parsed, false);
});
