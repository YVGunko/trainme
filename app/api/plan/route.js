import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

// Read the plan in force without asking the coach for a new one. A plan is kept
// for its whole stretch of days, so opening the page twice must not cost a call.
export async function GET(request) {
  try {
    await requireUser(request);
    const url = new URL(request.url);
    const date = url.searchParams.get('date') || '';
    const body = { adjust: false };
    if (/^\d{4}-\d{2}-\d{2}$/.test(date)) body.date = date;
    const result = await callRender('/recommend', body);
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 429 ? 429 : status === 503 ? 503 : 502;
    return Response.json({ ok: false, error: messageFor(status) }, { status: httpStatus });
  }
}

function messageFor(status) {
  if (status === 401) return 'Сервис не принял секрет';
  if (status === 429) return 'Garmin ограничил запросы. Подождите и повторите';
  if (status === 503) return 'Тренер не настроен: проверьте LLM_API_KEY';
  return 'План не получен. Подождите минуту и повторите';
}
