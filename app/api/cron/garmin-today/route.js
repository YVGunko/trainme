import { archivePeriodAndParse } from '@/server/archive-run';
import { cronAuthorized } from '@/server/cron-auth';
import { refreshHistory } from '@/server/history-refresh';
import { requestRecommendation } from '@/server/recommend';
import { trainingCalendarDate } from '@/lib/training-day';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

// Runs at 11:00 and 23:00 local time (08:00 and 20:00 UTC).
//
// Each run does three things in order, because each depends on the one before:
// read today from Garmin, refresh the rolling history window so the coach sees
// the sessions that just happened, then ask the coach. A step that fails stops
// the ones after it: advising on stale data is worse than not advising.
export async function GET(request) {
  if (!cronAuthorized(request.headers.get('authorization'), process.env.CRON_SECRET || '')) {
    return Response.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
  }
  const day = trainingCalendarDate();
  const report = { day, steps: {} };

  try {
    const { result, queue } = await archivePeriodAndParse(day, day);
    report.steps.archive = { ok: true, result, queue };
  } catch (error) {
    return failure(report, 'archive', error);
  }

  try {
    report.steps.history = { ok: true, result: await refreshHistory(day, HISTORY_DAYS) };
  } catch (error) {
    return failure(report, 'history', error);
  }

  try {
    report.steps.recommend = { ok: true, result: await requestRecommendation(day) };
  } catch (error) {
    // The data landed, so this is a coach problem, not a load problem.
    return failure(report, 'recommend', error);
  }

  return Response.json({ ok: true, ...report });
}

const HISTORY_DAYS = 10;

function failure(report, step, error) {
  const status = error?.status || 500;
  console.error(`cron step failed: ${step}`, status);
  const message =
    status === 401
      ? 'A service rejected the secret'
      : status === 503
        ? 'A service is not configured'
        : status === 429
          ? 'Garmin rate limited the run'
          : `The ${step} step failed`;
  return Response.json(
    { ok: false, error: message, ...report },
    { status: status === 503 ? 503 : status === 429 ? 429 : 502 },
  );
}
