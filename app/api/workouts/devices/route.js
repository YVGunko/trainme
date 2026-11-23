import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function POST(request) {
  try {
    await requireUser(request);
    const result = await callRender('/workouts/devices', {});
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Need to sign in' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 503 ? 503 : status === 429 ? 429 : 502;
    return Response.json({ ok: false, error: renderMessage(status) }, { status: httpStatus });
  }
}

function renderMessage(status) {
  if (status === 401) return 'The sending service rejected the secret';
  if (status === 429) return 'Garmin limited the requests. Wait and try again';
  if (status === 503) return 'The sending service is not configured';
  return 'The Garmin device list was not received. Wait a minute and try again';
}
