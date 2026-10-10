import crypto from 'node:crypto';

export const SESSION_COOKIE = 'tm_session';
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;
const SCRYPT_N = 16384;
const SCRYPT_R = 8;
const SCRYPT_P = 1;
const SCRYPT_KEY_LENGTH = 64;

function sessionSecret() {
  const secret = process.env.tm_SESSION_SECRET || '';
  if (!secret) {
    throw new Error('tm_SESSION_SECRET is missing');
  }
  return secret;
}

function base64UrlEncode(value) {
  return Buffer.from(value).toString('base64url');
}

function base64UrlDecode(value) {
  return Buffer.from(value, 'base64url').toString('utf8');
}

function hmac(value) {
  return crypto.createHmac('sha256', sessionSecret()).update(value).digest('base64url');
}

function safeEqual(a, b) {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}

export function hashPassword(password) {
  const salt = crypto.randomBytes(16);
  const derived = crypto.scryptSync(password, salt, SCRYPT_KEY_LENGTH, {
    N: SCRYPT_N,
    r: SCRYPT_R,
    p: SCRYPT_P,
  });
  return `scrypt$${SCRYPT_N}$${SCRYPT_R}$${SCRYPT_P}$${salt.toString('hex')}$${derived.toString('hex')}`;
}

export function parsePasswordHash(passwordHash) {
  const parts = String(passwordHash || '').split('$');
  if (parts.length !== 6 || parts[0] !== 'scrypt') return null;

  const [, n, r, p, saltHex, hashHex] = parts;
  const N = Number(n);
  const bigR = Number(r);
  const bigP = Number(p);

  if (!Number.isInteger(N) || !Number.isInteger(bigR) || !Number.isInteger(bigP)) return null;
  if (!saltHex || !hashHex) return null;

  return { N, r: bigR, p: bigP, saltHex, hashHex };
}

export function verifyPasswordHash(password, passwordHash) {
  try {
    const parsed = parsePasswordHash(passwordHash);
    if (!parsed) return false;

    const expected = Buffer.from(parsed.hashHex, 'hex');
    const attempts = [Buffer.from(parsed.saltHex, 'hex'), parsed.saltHex];

    for (const salt of attempts) {
      const derived = crypto.scryptSync(password, salt, expected.length, {
        N: parsed.N,
        r: parsed.r,
        p: parsed.p,
      });
      if (safeEqual(derived, expected)) return true;
    }

    return false;
  } catch {
    return false;
  }
}

export function createSessionToken(user, nowSeconds = Math.floor(Date.now() / 1000)) {
  const payload = {
    sub: user.id,
    username: user.username,
    exp: nowSeconds + SESSION_TTL_SECONDS,
  };
  const encodedPayload = base64UrlEncode(JSON.stringify(payload));
  const signature = hmac(encodedPayload);
  return `${encodedPayload}.${signature}`;
}

export function verifySessionToken(token) {
  if (!process.env.tm_SESSION_SECRET) return null;
  if (!token || typeof token !== 'string') return null;
  const [encodedPayload, signature] = token.split('.');
  if (!encodedPayload || !signature) return null;

  const expectedSignature = hmac(encodedPayload);
  if (!safeEqual(signature, expectedSignature)) return null;

  try {
    const payload = JSON.parse(base64UrlDecode(encodedPayload));
    if (!payload?.sub || !payload?.username || !payload?.exp) return null;
    if (Math.floor(Date.now() / 1000) > payload.exp) return null;
    return payload;
  } catch {
    return null;
  }
}

export function buildSessionCookie(token) {
  const secure = process.env.NODE_ENV === 'production';
  return [
    `${SESSION_COOKIE}=${token}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    secure ? 'Secure' : null,
    `Max-Age=${SESSION_TTL_SECONDS}`,
  ]
    .filter(Boolean)
    .join('; ');
}

export function clearSessionCookie() {
  const secure = process.env.NODE_ENV === 'production';
  return [
    `${SESSION_COOKIE}=`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    secure ? 'Secure' : null,
    'Max-Age=0',
  ]
    .filter(Boolean)
    .join('; ');
}

export function getSessionTokenFromRequest(request) {
  const cookieHeader = request.headers.get('cookie') || '';
  const match = cookieHeader.match(new RegExp(`${SESSION_COOKIE}=([^;]+)`));
  return match ? match[1] : null;
}
