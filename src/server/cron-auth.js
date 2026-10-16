import { timingSafeEqual } from 'node:crypto';

export function cronAuthorized(header, secret) {
  if (!secret) return false;
  const expected = Buffer.from(`Bearer ${secret}`);
  const given = Buffer.from(String(header || ''));
  if (given.length !== expected.length) return false;
  return timingSafeEqual(given, expected);
}
