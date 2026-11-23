import { callRender } from '@/server/render';
import { renderFailure } from '@/server/render-failure';
import { requireUser } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 60;

// A language check of the text currently in the field. The diary is not updated.
export async function POST(request) {
  try {
    await requireUser(request);
    const body = await request.json().catch(() => null);
    const text = typeof body?.text === 'string' ? body.text : '';
    const result = await callRender('/english', { text });
    return Response.json({ ok: true, result });
  } catch (error) {
    if (error?.message === 'unauthorized') {
      return Response.json({ ok: false, error: 'Need to sign in' }, { status: 401 });
    }
    const failure = renderFailure(error, 'The check failed. Wait and try again');
    const message = failure.status === 503 ? 'The English check is not configured' : failure.error;
    return Response.json({ ok: false, error: message }, { status: failure.status });
  }
}
