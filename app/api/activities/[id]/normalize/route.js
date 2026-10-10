import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(request, { params }) {
  try {
    await requireUser(request);
    const { id } = await params;
    if (!/^\d+$/.test(id)) {
      return Response.json({ ok: false, error: 'Тренировка не найдена' }, { status: 404 });
    }
    await callRender('/normalize', { garmin_activity_id: id });
    return Response.json({ ok: true });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 404 ? 404 : status === 503 ? 503 : 502;
    return Response.json({ ok: false, error: renderMessage(status) }, { status: httpStatus });
  }
}

function renderMessage(status) {
  if (status === 401) return 'Сервис разбора не принял секрет';
  if (status === 503) return 'Сервис разбора не настроен';
  if (status === 404) return 'Файл тренировки ещё не загружен';
  return 'Разбор не удался. Подождите минуту и повторите';
}
