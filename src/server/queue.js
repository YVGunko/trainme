import { QueueClient } from '@vercel/queue';

import { enqueueActivityParses } from '@/server/activity-queue';

export function publishActivityParses(result) {
  const client = new QueueClient({
    region: process.env.VERCEL_REGION || 'iad1',
    token: process.env.VERCEL_OIDC_TOKEN || undefined,
    deploymentId: process.env.VERCEL_DEPLOYMENT_ID || null,
  });
  return enqueueActivityParses(result, (topic, payload) => client.send(topic, payload));
}
