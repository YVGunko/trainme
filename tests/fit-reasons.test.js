import assert from 'node:assert/strict';
import test from 'node:test';
import { FIT_REASONS, fitReason } from '../src/lib/fit-reasons.js';

test('an activity file is explained as an activity, not a workout', () => {
  const text = fitReason('activity_file');
  assert.match(text, /активности/);
  assert.match(text, /не тренировки/);
  // The user has to be told that Garmin has no workout import at all,
  // otherwise trying another FIT file looks like the right next step.
  assert.match(text, /не импортирует FIT-тренировки/);
});

test('every known reason has its own sentence', () => {
  const sentences = Object.values(FIT_REASONS);
  assert.equal(new Set(sentences).size, sentences.length);
  for (const [reason, sentence] of Object.entries(FIT_REASONS)) {
    assert.ok(sentence.length > 10, `${reason} needs a real sentence`);
  }
});

test('an unknown reason gives an empty sentence instead of undefined', () => {
  assert.equal(fitReason('something_new'), '');
  assert.equal(fitReason(null), '');
});
