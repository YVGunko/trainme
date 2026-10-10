import assert from 'node:assert/strict';
import test from 'node:test';
import { filterActivities, sortActivities, toggleSort } from '../src/lib/table.js';

const rows = [
  {
    garminActivityId: '2',
    whenSort: '2026-10-07 18:47',
    title: 'Bike',
    description: 'интервалы',
    sport: 'cycling',
    durationSec: 100,
    distanceM: 1000,
    parsed: true,
  },
  {
    garminActivityId: '3',
    whenSort: null,
    title: '—',
    description: '',
    sport: '—',
    durationSec: null,
    distanceM: null,
    parsed: false,
  },
  {
    garminActivityId: '1',
    whenSort: '2026-10-10 07:21',
    title: 'Morning run',
    description: 'легко',
    sport: 'running',
    durationSec: 200,
    distanceM: 5000,
    parsed: true,
  },
];

test('default date order is newest first and undated rows stay last', () => {
  const sorted = sortActivities(rows, [{ id: 'when', desc: true }]);
  assert.deepEqual(
    sorted.map((row) => row.garminActivityId),
    ['1', '2', '3']
  );
});

test('shift click adds a second sort without dropping the date', () => {
  const sorting = toggleSort([{ id: 'when', desc: true }], 'title', true);
  assert.deepEqual(sorting, [
    { id: 'when', desc: true },
    { id: 'title', desc: false },
  ]);
  const sorted = sortActivities(rows, sorting);
  assert.equal(sorted[0].garminActivityId, '1');
  assert.equal(sorted.at(-1).garminActivityId, '3');
});

test('search looks only at title and description', () => {
  assert.deepEqual(
    filterActivities(rows, 'интер').map((row) => row.garminActivityId),
    ['2']
  );
  assert.deepEqual(
    filterActivities(rows, 'running').map((row) => row.garminActivityId),
    []
  );
});
