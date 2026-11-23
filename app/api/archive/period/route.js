import { archivePeriodAndParse } from '@/server/archive-run';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

const DAY_MS = 24 * 60 * 60 * 1000;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json();
    const start = typeof body?.start === 'string' ? body.start : '';
    const end = typeof body?.end === 'string' ? body.end : '';
    if (!validPeriod(start, end)) {
      return Response.json(
        { ok: false, error: 'Need two dates, the end not before the start, and a period no longer than 14 days' },
        { status: 400 }
      );
    }
    const { result, queue } = await archivePeriodAndParse(start, end);
    return Response.json({ ok: true, result, queue });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Need to sign in' }, { status: 401 });
    }
    const status = error?.status || 500;
    const message =
      status === 400
        ? 'Check the dates. The period is no longer than 14 days'
        : status === 401
          ? 'The download service rejected the secret'
          : status === 503
            ? 'The download service is not configured'
            : 'Download failed. Wait a minute and try again';
    const httpStatus = status === 400 || status === 503 ? status : 502;
    return Response.json({ ok: false, error: message }, { status: httpStatus });
  }
}

function validPeriod(start, end) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return false;
  const startDate = Date.parse(`${start}T00:00:00Z`);
  const endDate = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(startDate) || !Number.isFinite(endDate) || endDate < startDate) return false;
  return Math.round((endDate - startDate) / DAY_MS) + 1 <= 14;
}
