import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    if (!body || typeof body !== 'object' || typeof body.workout !== 'object' || body.workout === null) {
      return Response.json({ ok: false, error: 'A workout description is required' }, { status: 400 });
    }
    const result = await callRender('/workouts', body);
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Need to sign in' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 400 || status === 503 ? status : status === 429 ? 429 : 502;
    return Response.json({ ok: false, error: renderMessage(status, error?.detail) }, { status: httpStatus });
  }
}

function renderMessage(status, detail) {
  const notPushed = typeof detail === 'string' ? detail.match(/Workout (\d+) was uploaded/) : null;
  if (notPushed) return `Workout ${notPushed[1]} is in the library but was not sent to the device`;
  if (status === 400) return 'The workout did not pass the check';
  if (status === 401) return 'The sending service rejected the secret';
  if (status === 429) return 'Garmin limited the requests. Wait and try again';
  if (status === 503) return 'The sending service is not configured';
  return 'Sending the workout failed. Wait a minute and try again';
}
