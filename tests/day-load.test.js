import assert from 'node:assert/strict';
import test from 'node:test';

import { dayLoadVisible, requestDayLoad } from '../src/lib/day-load.js';

test('the load control is only for a day that has no Garmin row', () => {
  assert.equal(dayLoadVisible(null), true);
  assert.equal(dayLoadVisible(undefined), false);
  assert.equal(dayLoadVisible({}), false);
  assert.equal(dayLoadVisible({ sleep_duration_sec: 3600 }), false);
});

test('load archives the open day and then reads that day once', async () => {
  const calls = [];
  const result = await requestDayLoad('2026-11-21', async (url, options = {}) => {
    calls.push({ url, method: options.method || 'GET', body: options.body });
    if (url === '/api/archive/period') {
      return json({ ok: true });
    }
    return json({ ok: true, garmin: { resting_hr: 48 }, wellness: null });
  });

  assert.deepEqual(calls, [
    {
      url: '/api/archive/period',
      method: 'POST',
      body: JSON.stringify({ start: '2026-11-21', end: '2026-11-21' }),
    },
    { url: '/api/days/2026-11-21', method: 'GET', body: undefined },
  ]);
  assert.deepEqual(result, { ok: true, garmin: { resting_hr: 48 }, wellness: null });
});

test('a failed archive does not read the day', async () => {
  const calls = [];
  const result = await requestDayLoad('2026-11-21', async (url) => {
    calls.push(url);
    return json({ ok: false, error: 'Download failed. Wait a minute and try again' }, 502);
  });

  assert.deepEqual(calls, ['/api/archive/period']);
  assert.deepEqual(result, {
    ok: false,
    error: 'Download failed. Wait a minute and try again',
  });
});

function json(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}
