import { verifySessionToken } from '@/lib/auth';
import { getPrisma } from '@/server/db';

export async function userFromToken(token) {
  const payload = verifySessionToken(token);
  if (!payload) return null;
  const prisma = getPrisma();
  const user = await prisma.users.findUnique({
    where: { id: payload.sub },
    select: { id: true, username: true, is_active: true },
  });
  if (!user?.is_active) return null;
  return { id: user.id, username: user.username };
}
