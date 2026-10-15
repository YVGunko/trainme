import { handleCallback } from '@vercel/queue';

import { callRender } from '@/server/render';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export const POST = handleCallback(async (message) => {
  const id = message?.garminActivityId;
  if (typeof id !== 'number' || !Number.isInteger(id) || id < 1) {
    throw new Error('garminActivityId is required');
  }
  await callRender('/normalize', { garmin_activity_id: id });
});
