import { getRender } from '@/server/render';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function GET(request) {
  try {
    await requireUser(request);
    const result = await getRender('/context');
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const status = error?.status || 500;
    const httpStatus = status === 503 ? 503 : 502;
    return Response.json({ ok: false, error: messageFor(status) }, { status: httpStatus });
  }
}

function messageFor(status) {
  if (status === 401) return 'Сервис не принял секрет';
  if (status === 503) return 'Сервис контекста не настроен';
  return 'Контекст недоступен. Подождите минуту и повторите';
}
