import assert from 'node:assert/strict';
import test from 'node:test';
import { renderFailure } from '../src/server/render-failure.js';

test('a missing route means the service build is old, not a bug to debug', () => {
  const failure = renderFailure({ status: 404 }, 'The context is unavailable');
  assert.equal(failure.status, 502);
  assert.match(failure.error, /has not updated/);
  assert.match(failure.error, /Wait/);
});

test('a real failure shows what the service said', () => {
  const failure = renderFailure(
    { status: 502, detail: 'Context read failed: UndefinedColumn' },
    'The context is unavailable',
  );
  assert.equal(failure.status, 502);
  // The class name is the whole point: it names the cause without server logs.
  assert.match(failure.error, /UndefinedColumn/);
});

test('a 502 without a detail falls back to the caller sentence', () => {
  const failure = renderFailure({ status: 502 }, 'The context is unavailable');
  assert.equal(failure.error, 'The context is unavailable');
});

test('an unconfigured service is not retried', () => {
  const failure = renderFailure({ status: 503 }, 'x');
  assert.equal(failure.status, 503);
  assert.match(failure.error, /not configured/);
});

test('a rate limit stays a rate limit', () => {
  const failure = renderFailure({ status: 429 }, 'x');
  assert.equal(failure.status, 429);
  assert.match(failure.error, /limited/);
});

test('a bad request is the reader typo, so it stays 400', () => {
  const failure = renderFailure({ status: 400 }, 'x');
  assert.equal(failure.status, 400);
});

test('an error with no status means the service did not answer', () => {
  const failure = renderFailure(new Error('fetch failed'), 'x');
  assert.equal(failure.status, 502);
  assert.match(failure.error, /did not answer/);
});

test('a missing secret is reported as unconfigured, not as an outage', () => {
  const failure = renderFailure({ status: 401 }, 'x');
  assert.equal(failure.status, 401);
  assert.match(failure.error, /secret/);
});
