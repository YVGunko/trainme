import { callRender } from '@/server/render';
import { renderFailure } from '@/server/render-failure';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

const DAY_MS = 24 * 60 * 60 * 1000;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    const start = typeof body?.start === 'string' ? body.start : '';
    const end = typeof body?.end === 'string' ? body.end : '';
    if (!validPeriod(start, end)) {
      return Response.json(
        { ok: false, error: 'Need two dates, the end not before the start, and a period no longer than 400 days' },
        { status: 400 },
      );
    }
    const result = await callRender('/history', { start, end });
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Need to sign in' }, { status: 401 });
    }
    const failure = renderFailure(error, 'History was not loaded');
    // A bad period is the athlete's typo, so keep it a 400.
    const status = failure.status === 502 && error?.status === 400 ? 400 : failure.status;
    return Response.json({ ok: false, error: failure.error }, { status });
  }
}

function validPeriod(start, end) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return false;
  const startDate = Date.parse(`${start}T00:00:00Z`);
  const endDate = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(startDate) || !Number.isFinite(endDate) || endDate < startDate) return false;
  return Math.round((endDate - startDate) / DAY_MS) + 1 <= 400;
}
