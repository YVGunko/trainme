import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import { ACTIVITY_NORMALIZE_TOPIC, enqueueActivityParses, newActivityIds } from '../src/server/activity-queue.js';

test('new activity ids are the files stored in this archive call', () => {
  assert.deepEqual(
    newActivityIds({
      activities: [
        { garmin_activity_id: 9, stored: false },
        { garmin_activity_id: '8', stored: true },
        { garmin_activity_id: 7, stored: true },
        { garmin_activity_id: 0, stored: true },
        { stored: true },
      ],
    }),
    [8, 7]
  );
  assert.deepEqual(newActivityIds({}), []);
});

test('a failed queue send is reported and does not stop the other ids', async () => {
  const sent = [];
  const result = await enqueueActivityParses(
    {
      activities: [
        { garmin_activity_id: 9, stored: true },
        { garmin_activity_id: 8, stored: true },
      ],
    },
    async (topic, payload) => {
      sent.push([topic, payload]);
      if (payload.garminActivityId === 8) throw new Error('queue unavailable');
    }
  );
  assert.deepEqual(sent, [
    [ACTIVITY_NORMALIZE_TOPIC, { garminActivityId: 9 }],
    [ACTIVITY_NORMALIZE_TOPIC, { garminActivityId: 8 }],
  ]);
  assert.deepEqual(result, { queued: [9], failed: [{ garminActivityId: 8 }] });
});

test('vercel.json registers the activity normalize consumer', () => {
  const config = JSON.parse(fs.readFileSync(new URL('../vercel.json', import.meta.url), 'utf8'));
  const trigger = config?.functions?.['app/api/queue/activity-normalize/route.js']?.experimentalTriggers?.[0];
  assert.deepEqual(trigger, {
    type: 'queue/v2beta',
    topic: ACTIVITY_NORMALIZE_TOPIC,
    retryAfterSeconds: 60,
    initialDelaySeconds: 0,
  });
});
