import { PrismaClient } from '@prisma/client';

export function getPrisma() {
  const url = process.env.DATABASE_URL || process.env.tm_DATABASE_URL || '';
  if (!url) {
    const error = new Error('database is not configured');
    error.status = 503;
    throw error;
  }
  process.env.DATABASE_URL = url;
  if (!globalThis.__trainmePrisma) {
    globalThis.__trainmePrisma = new PrismaClient({
      log: process.env.NODE_ENV === 'development' ? ['error'] : [],
    });
  }
  return globalThis.__trainmePrisma;
}
