import { clearSessionCookie, getSessionTokenFromRequest } from '@/lib/auth';
import { userFromToken } from '@/server/session';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(request) {
  try {
    const user = await userFromToken(getSessionTokenFromRequest(request));
    if (!user) {
      return Response.json(
        { ok: false, authenticated: false },
        { status: 401, headers: { 'Set-Cookie': clearSessionCookie() } }
      );
    }
    return Response.json({ ok: true, authenticated: true, user });
  } catch {
    console.error('session lookup failed');
    return Response.json({ ok: false, authenticated: false }, { status: 500 });
  }
}
