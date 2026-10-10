import { hashPassword, verifyPasswordHash } from '@/lib/auth';
import { getPrisma } from '@/server/db';

const CREATE_USERS = `
CREATE TABLE IF NOT EXISTS users (
    id text PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)`;

function configuredAccount() {
  const username = (process.env.tm_AUTH_USERNAME || '').trim();
  const password = process.env.tm_AUTH_PASSWORD || '';
  if (!username || !password || !process.env.tm_SESSION_SECRET) {
    const error = new Error('auth is not configured');
    error.status = 503;
    throw error;
  }
  return { username, password };
}

export async function ensureLoginUser() {
  const { username, password } = configuredAccount();
  const prisma = getPrisma();
  await prisma.$executeRawUnsafe(CREATE_USERS);
  const existing = await prisma.users.findUnique({
    where: { username },
    select: { id: true, username: true, password_hash: true, is_active: true },
  });
  if (existing && verifyPasswordHash(password, existing.password_hash)) {
    if (!existing.is_active) {
      return prisma.users.update({
        where: { id: existing.id },
        data: { is_active: true },
        select: { id: true, username: true, password_hash: true, is_active: true },
      });
    }
    return existing;
  }
  const password_hash = hashPassword(password);
  return prisma.users.upsert({
    where: { username },
    update: { password_hash, is_active: true },
    create: { username, password_hash, is_active: true },
    select: { id: true, username: true, password_hash: true, is_active: true },
  });
}
