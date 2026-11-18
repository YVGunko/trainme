import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

const MAX_BASE64_LENGTH = 360 * 1024;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    const content = typeof body?.content_base64 === 'string' ? body.content_base64 : '';
    if (!content) {
      return Response.json({ ok: false, error: 'Нужен файл FIT' }, { status: 400 });
    }
    if (content.length > MAX_BASE64_LENGTH) {
      return Response.json({ ok: false, error: 'Файл больше 256 КБ' }, { status: 400 });
    }
    const result = await callRender('/workouts/fit', body);
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
  if (status === 400) return 'Файл FIT не разобран как тренировка';
  if (status === 401) return 'Сервис отправки не принял секрет';
  if (status === 429) return 'Garmin ограничил запросы. Подождите и повторите';
  if (status === 503) return 'Сервис отправки не настроен';
  return 'Загрузка файла FIT не удалась. Подождите минуту и повторите';
}
