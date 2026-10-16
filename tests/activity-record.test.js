import assert from 'node:assert/strict';
import test from 'node:test';
import { describeActivity, strengthSetLine } from '../src/lib/activity-record.js';

test('an unparsed workout shows only the list facts', () => {
  const view = describeActivity({
    parsed: false,
    when: '2026-10-16 07:30',
    garminName: 'Morning ride',
    avgHr: 140,
    cycling: { avgPowerW: 180 },
  });
  assert.deepEqual(view.facts, [
    { label: 'When', value: '2026-10-16 07:30' },
    { label: 'Garmin name', value: 'Morning ride' },
  ]);
  assert.deepEqual(view.sets, []);
});

test('a parsed ride shows garmin totals as text and hides empty facts', () => {
  const view = describeActivity({
    parsed: true,
    when: '2026-10-16 07:30',
    garminName: 'Morning ride',
    sport: 'cycling',
    subSport: 'indoor_cycling',
    durationSec: 3600,
    distanceM: 30000,
    avgHr: 140,
    avgSpeed: 8.333,
    calories: null,
    cycling: {
      avgPowerW: 180,
      normalizedPowerW: 190,
      totalWorkJ: 648000,
    },
    running: null,
    sets: [],
  });
  const labels = view.facts.map((fact) => fact.label);
  assert.equal(labels.includes('Calories'), false);
  assert.equal(labels.includes('Average heart rate'), true);
  assert.deepEqual(
    view.facts.find((fact) => fact.label === 'Average speed'),
    { label: 'Average speed', value: '30 km/h' }
  );
  assert.deepEqual(
    view.facts.find((fact) => fact.label === 'Distance'),
    { label: 'Distance', value: '30.00 km' }
  );
  assert.deepEqual(
    view.facts.find((fact) => fact.label === 'Work'),
    { label: 'Work', value: '648 kJ' }
  );
});

test('a strength set is one readable line', () => {
  assert.equal(
    strengthSetLine({ exercise: 'Bench press', repetitions: 8, weightKg: 40, setType: 'active' }),
    'Bench press · 8 reps · 40 kg'
  );
  const view = describeActivity({
    parsed: true,
    sets: [
      { exercise: 'Squat', repetitions: 5, weightKg: 60, setType: 'active' },
      { category: 'rest', setType: 'rest', durationSec: 90 },
    ],
  });
  assert.deepEqual(view.sets, ['Squat · 5 reps · 60 kg', 'rest · 1:30']);
});
