import { archivePeriodAndParse } from '@/server/archive-run';
import { cronAuthorized } from '@/server/cron-auth';
import { trainingCalendarDate } from '@/lib/training-day';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function GET(request) {
  if (!cronAuthorized(request.headers.get('authorization'), process.env.CRON_SECRET || '')) {
    return Response.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
  }
  const day = trainingCalendarDate();
  try {
    const { result, queue } = await archivePeriodAndParse(day, day);
    return Response.json({ ok: true, day, result, queue });
  } catch (error) {
    const status = error?.status || 500;
    console.error('today garmin load failed', status);
    const message =
      status === 401
        ? 'Load service rejected the secret'
        : status === 503
          ? 'Load service is not configured'
          : "Today's Garmin load failed";
    const httpStatus = status === 503 ? 503 : 502;
    return Response.json({ ok: false, error: message }, { status: httpStatus });
  }
}
