import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

// Ask the coach for a revision of the plan in force. This is the button a person
// presses after something changed that the schedule has not seen yet.
export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    const payload = { adjust: true };
    const date = typeof body?.date === 'string' ? body.date : '';
    if (/^\d{4}-\d{2}-\d{2}$/.test(date)) payload.date = date;
    if (body?.regenerate === true) payload.regenerate = true;
    const result = await callRender('/recommend', payload);
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 429 ? 429 : status === 503 ? 503 : 502;
    return Response.json({ ok: false, error: messageFor(status, error?.detail) }, { status: httpStatus });
  }
}

function messageFor(status, detail) {
  if (status === 401) return 'Сервис не принял секрет';
  if (status === 429) return 'Тренер ограничил запросы. Подождите и повторите';
  if (status === 503) return 'Тренер не настроен: проверьте LLM_API_KEY';
  if (typeof detail === 'string' && detail) return `Тренер не смог пересчитать план: ${detail}`;
  return 'Тренер не смог пересчитать план. Подождите минуту и повторите';
}
