import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    const date = typeof body?.date === 'string' ? body.date : '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return Response.json({ ok: false, error: 'Need a date as YYYY-MM-DD' }, { status: 400 });
    }
    const result = await callRender('/workouts/strength-test', { date });
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
  const uploaded = typeof detail === 'string' ? detail.match(/Workout (\d+) was uploaded/) : null;
  if (uploaded) return `Workout ${uploaded[1]} is in the library but was not scheduled`;
  if (status === 400) return 'Need a date as YYYY-MM-DD';
  if (status === 401) return 'The sending service rejected the secret';
  if (status === 429) return 'Garmin limited the requests. Wait and try again';
  if (status === 503) return 'The sending service is not configured';
  return 'Sending the workout failed. Wait a minute and try again';
}
