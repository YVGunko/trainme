import { publishActivityParses } from '@/server/queue';
import { callRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

const DAY_MS = 24 * 60 * 60 * 1000;

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json();
    const start = typeof body?.start === 'string' ? body.start : '';
    const end = typeof body?.end === 'string' ? body.end : '';
    if (!validPeriod(start, end)) {
      return Response.json(
        { ok: false, error: 'Нужны две даты, конец не раньше начала, период не длиннее 14 дней' },
        { status: 400 }
      );
    }
    const result = await callRender('/archive/period', { start, end });
    const queue = await publishActivityParses(result);
    return Response.json({ ok: true, result, queue });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const message =
      status === 400
        ? 'Проверьте даты. Период не длиннее 14 дней'
        : status === 401
          ? 'Сервис загрузки не принял секрет'
          : status === 503
            ? 'Сервис загрузки не настроен'
            : 'Загрузка не удалась. Подождите минуту и повторите';
    const httpStatus = status === 400 || status === 503 ? status : 502;
    return Response.json({ ok: false, error: message }, { status: httpStatus });
  }
}

function validPeriod(start, end) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return false;
  const startDate = Date.parse(`${start}T00:00:00Z`);
  const endDate = Date.parse(`${end}T00:00:00Z`);
  if (!Number.isFinite(startDate) || !Number.isFinite(endDate) || endDate < startDate) return false;
  return Math.round((endDate - startDate) / DAY_MS) + 1 <= 14;
}
