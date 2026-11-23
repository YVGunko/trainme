import { getRender } from '@/server/render';
import { renderFailure } from '@/server/render-failure';
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
      return Response.json({ ok: false, error: 'Need to sign in' }, { status: 401 });
    }
    const failure = renderFailure(error, 'The context is unavailable');
    return Response.json({ ok: false, error: failure.error }, { status: failure.status });
  }
}
