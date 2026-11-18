import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

const DAY_MS = 24 * 60 * 60 * 1000;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    const start = typeof body?.start === 'string' ? body.start : '';
    const end = typeof body?.end === 'string' ? body.end : '';
    if (!validPeriod(start, end)) {
      return Response.json(
        { ok: false, error: 'Нужны две даты, конец не раньше начала, период не длиннее 400 дней' },
        { status: 400 },
      );
    }
    const result = await callRender('/history', { start, end });
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 400 || status === 503 ? status : status === 429 ? 429 : 502;
    return Response.json({ ok: false, error: messageFor(status) }, { status: httpStatus });
  }
}

function validPeriod(start, end) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return false;
  const startDate = Date.parse(`${start}T00:00:00Z`);
  const endDate = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(startDate) || !Number.isFinite(endDate) || endDate < startDate) return false;
  return Math.round((endDate - startDate) / DAY_MS) + 1 <= 400;
}

function messageFor(status) {
  if (status === 400) return 'Проверьте даты. Период не длиннее 400 дней';
  if (status === 401) return 'Сервис не принял секрет';
  if (status === 429) return 'Garmin ограничил запросы. Подождите и повторите';
  if (status === 503) return 'Сервис истории не настроен';
  return 'Загрузка истории не удалась. Подождите минуту и повторите';
}
