import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function POST(request) {
  try {
    await requireUser(request);
    const result = await callRender('/workouts/devices', {});
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 503 ? 503 : status === 429 ? 429 : 502;
    return Response.json({ ok: false, error: renderMessage(status) }, { status: httpStatus });
  }
}

function renderMessage(status) {
  if (status === 401) return 'Сервис отправки не принял секрет';
  if (status === 429) return 'Garmin ограничил запросы. Подождите и повторите';
  if (status === 503) return 'Сервис отправки не настроен';
  return 'Список устройств Garmin не получен. Подождите минуту и повторите';
}
