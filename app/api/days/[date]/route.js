import { parseCalendarDate, parseWellness } from '@/lib/wellness';
import { readDay, saveWellness } from '@/server/day';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request, { params }) {
  const { date } = await params;
  return respond(() => load(request, date));
}

export async function POST(request, { params }) {
  const { date: rawDate } = await params;
  return respond(async () => {
    await requireUser(request);
    const date = parseCalendarDate(rawDate);
    let body;
    try {
      body = await request.json();
    } catch {
      const error = new Error('Could not save.');
      error.status = 400;
      error.publicMessage = 'Could not save.';
      throw error;
    }
    const row = parseWellness(body);
    const day = await saveWellness(date, row);
    return { ok: true, ...day };
  }, 'Could not save.');
}

async function load(request, rawDate) {
  await requireUser(request);
  const date = parseCalendarDate(rawDate);
  const day = await readDay(date);
  return { ok: true, ...day };
}

async function respond(work, fallback = 'Could not load this day.') {
  try {
    return Response.json(await work());
  } catch (error) {
    const status = error?.status === 401 ? 401 : error?.status === 400 ? 400 : error?.status === 503 ? 503 : 500;
    const message =
      status === 401
        ? 'Sign in required.'
        : status === 503
          ? 'Day storage is not configured.'
          : status === 400
            ? error.publicMessage || 'Could not save.'
            : fallback;
    if (status === 500) console.error('day card failed');
    return Response.json({ ok: false, error: message }, { status });
  }
}
