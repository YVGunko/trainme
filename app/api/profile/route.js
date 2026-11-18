import { callRender, getRender } from '@/server/render';
import { renderFailure } from '@/server/render-failure';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 120;

export async function GET(request) {
  try {
    await requireUser(request);
    const result = await getRender('/profile');
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const failure = renderFailure(error, 'Профиль недоступен');
    return Response.json({ ok: false, error: failure.error }, { status: failure.status });
  }
}

export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    if (!body || typeof body !== 'object') {
      return Response.json({ ok: false, error: 'Нужен профиль' }, { status: 400 });
    }
    const result = await callRender('/profile', body);
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Нужно войти' }, { status: 401 });
    }
    const failure = renderFailure(error, 'Профиль не сохранён');
    return Response.json({ ok: false, error: failure.error }, { status: failure.status });
  }
}
