import assert from 'node:assert/strict';
import test from 'node:test';
import {
  FIT_REASONS,
  fitReason,
  hasNumericWarning,
  warningText,
  warningTexts,
} from '../src/lib/fit-reasons.js';

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

test('a wrong-unit step is named with its real length', () => {
  const text = warningText({ code: 'short_steps', count: 16, smallest: 0.06 });
  assert.match(text, /16/);
  assert.match(text, /0\.1 с/);
  // The consequence is the point: Garmin would accept this as a real workout.
  assert.match(text, /несколько секунд/);
});

test('a whole workout under a minute is named with its total', () => {
  const text = warningText({ code: 'short_workout', total_seconds: 4.2 });
  assert.match(text, /4\.2 с/);
  assert.match(text, /ошибка в файле/);
});

test('dropped step names are a plain note, not a value problem', () => {
  const text = warningText({ code: 'step_names_dropped', count: 16 });
  assert.match(text, /16/);
  assert.equal(hasNumericWarning([{ code: 'step_names_dropped', count: 16 }]), false);
});

test('a value warning is recognised so it can be shown in red', () => {
  assert.equal(hasNumericWarning([{ code: 'short_steps', count: 1, smallest: 0.2 }]), true);
  assert.equal(hasNumericWarning([{ code: 'short_workout', total_seconds: 5 }]), true);
  assert.equal(hasNumericWarning([]), false);
  assert.equal(hasNumericWarning(null), false);
});

test('an unknown warning code is skipped instead of rendering nothing useful', () => {
  assert.equal(warningText({ code: 'brand_new' }), '');
  assert.deepEqual(warningTexts([{ code: 'brand_new' }, { code: 'short_workout', total_seconds: 3 }]), [
    warningText({ code: 'short_workout', total_seconds: 3 }),
  ]);
});

test('a real file keeps its notes apart from the result', () => {
  const warnings = [
    { code: 'step_names_dropped', count: 16 },
    { code: 'notes_dropped', count: 16 },
  ];
  const texts = warningTexts(warnings);
  assert.equal(texts.length, 2);
  assert.equal(hasNumericWarning(warnings), false);
});
