import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createSessionToken,
  hashPassword,
  verifyPasswordHash,
  verifySessionToken,
} from '../src/lib/auth.js';

test('scrypt hash verifies the same password and rejects another', () => {
  const hash = hashPassword('correct horse');
  assert.equal(verifyPasswordHash('correct horse', hash), true);
  assert.equal(verifyPasswordHash('other horse', hash), false);
  assert.equal(verifyPasswordHash('correct horse', 'not-a-hash'), false);
});

test('session token verifies and rejects tampering or expiry', () => {
  const previous = process.env.tm_SESSION_SECRET;
  process.env.tm_SESSION_SECRET = 'test-secret';
  try {
    const token = createSessionToken({ id: 'user-1', username: 'yg' });
    assert.deepEqual(verifySessionToken(token), {
      sub: 'user-1',
      username: 'yg',
      exp: JSON.parse(Buffer.from(token.split('.')[0], 'base64url').toString()).exp,
    });

    const [payload, signature] = token.split('.');
    assert.equal(verifySessionToken(`${payload.slice(0, -2)}aa.${signature}`), null);
    assert.equal(verifySessionToken(`${payload}.${signature.slice(0, -2)}aa`), null);

    const expired = createSessionToken({ id: 'user-1', username: 'yg' }, 1_000);
    assert.equal(verifySessionToken(expired), null);
  } finally {
    if (previous == null) delete process.env.tm_SESSION_SECRET;
    else process.env.tm_SESSION_SECRET = previous;
  }
});

test('signing requires tm_SESSION_SECRET', () => {
  const previous = process.env.tm_SESSION_SECRET;
  delete process.env.tm_SESSION_SECRET;
  try {
    assert.throws(() => createSessionToken({ id: 'user-1', username: 'yg' }));
    assert.equal(verifySessionToken('anything.else'), null);
  } finally {
    if (previous != null) process.env.tm_SESSION_SECRET = previous;
  }
});
