import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import { cronAuthorized } from '../src/server/cron-auth.js';
import { trainingCalendarDate } from '../src/lib/training-day.js';

test('the training day is the UTC+3 calendar date', () => {
  assert.equal(trainingCalendarDate(new Date('2026-10-16T05:30:00Z')), '2026-10-16');
  assert.equal(trainingCalendarDate(new Date('2026-10-16T06:00:00Z')), '2026-10-16');
  assert.equal(trainingCalendarDate(new Date('2026-10-16T18:30:00Z')), '2026-10-16');
  assert.equal(trainingCalendarDate(new Date('2026-10-16T20:59:00Z')), '2026-10-16');
  assert.equal(trainingCalendarDate(new Date('2026-10-16T21:00:00Z')), '2026-10-17');
});

test('cron auth accepts only the bearer secret', () => {
  assert.equal(cronAuthorized('Bearer secret-value', 'secret-value'), true);
  assert.equal(cronAuthorized('Bearer other-value', 'secret-value'), false);
  assert.equal(cronAuthorized('', 'secret-value'), false);
  assert.equal(cronAuthorized('Bearer secret-value', ''), false);
});

test('vercel.json runs the Garmin load at 09:00 and 21:00 UTC+3', () => {
  const config = JSON.parse(fs.readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
  assert.deepEqual(config.crons, [
    { path: '/api/cron/garmin-today', schedule: '0 6 * * *' },
    { path: '/api/cron/garmin-today', schedule: '0 18 * * *' },
  ]);
});
