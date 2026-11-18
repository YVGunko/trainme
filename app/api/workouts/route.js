import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    if (!body || typeof body !== 'object' || typeof body.workout !== 'object' || body.workout === null) {
      return Response.json({ ok: false, error: 'Нужно описание тренировки' }, { status: 400 });
    }
    const result = await callRender('/workouts', body);
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 400 || status === 503 ? status : status === 429 ? 429 : 502;
    return Response.json({ ok: false, error: renderMessage(status, error?.detail) }, { status: httpStatus });
  }
}

function renderMessage(status, detail) {
  const notPushed = typeof detail === 'string' ? detail.match(/Workout (\d+) was uploaded/) : null;
  if (notPushed) return `Шаблон ${notPushed[1]} загружен в библиотеку, но не отправлен на устройство`;
  if (status === 400) return 'Тренировка не прошла проверку';
  if (status === 401) return 'Сервис отправки не принял секрет';
  if (status === 429) return 'Garmin ограничил запросы. Подождите и повторите';
  if (status === 503) return 'Сервис отправки не настроен';
  return 'Отправка тренировки не удалась. Подождите минуту и повторите';
}
