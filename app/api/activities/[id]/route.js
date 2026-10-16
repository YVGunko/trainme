import { readActivityRecord } from '@/server/activity-record';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request, { params }) {
  try {
    await requireUser(request);
    const { id } = await params;
    if (!/^\d+$/.test(id)) {
      return Response.json({ ok: false, error: 'Workout not found.' }, { status: 404 });
    }
    const record = await readActivityRecord(id);
    if (!record) {
      return Response.json({ ok: false, error: 'Workout not found.' }, { status: 404 });
    }
    return Response.json({ ok: true, record });
  } catch (error) {
    const status = error?.status === 401 ? 401 : error?.status === 503 ? 503 : 500;
    const message =
      status === 401 ? 'Sign in required.' : status === 503 ? 'Workout storage is not configured.' : 'Could not load this workout.';
    if (status === 500) console.error('workout read failed');
    return Response.json({ ok: false, error: message }, { status });
  }
}
