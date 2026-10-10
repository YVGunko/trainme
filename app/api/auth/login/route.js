import { buildSessionCookie, createSessionToken, verifyPasswordHash } from '@/lib/auth';
import { getPrisma } from '@/server/db';
import { ensureLoginUser } from '@/server/users';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request) {
  try {
    const body = await request.json();
    const username = typeof body?.username === 'string' ? body.username.trim() : '';
    const password = typeof body?.password === 'string' ? body.password : '';

    if (!username || !password) {
      return Response.json({ ok: false, error: 'Нужны логин и пароль' }, { status: 400 });
    }
    if (username.length > 100 || password.length > 1024) {
      return Response.json({ ok: false, error: 'Неверный логин или пароль' }, { status: 401 });
    }

    await ensureLoginUser();
    const user = await getPrisma().users.findUnique({
      where: { username },
      select: { id: true, username: true, password_hash: true, is_active: true },
    });

    if (!user || !user.is_active || !verifyPasswordHash(password, user.password_hash)) {
      return Response.json({ ok: false, error: 'Неверный логин или пароль' }, { status: 401 });
    }

    return Response.json(
      { ok: true, user: { id: user.id, username: user.username } },
      { headers: { 'Set-Cookie': buildSessionCookie(createSessionToken(user)) } }
    );
  } catch (error) {
    const status = error?.status === 503 ? 503 : 500;
    console.error(status === 503 ? 'login is not configured' : 'login failed');
    return Response.json(
      { ok: false, error: status === 503 ? 'Вход не настроен' : 'Вход не удался' },
      { status }
    );
  }
}
