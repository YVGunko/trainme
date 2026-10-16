import assert from 'node:assert/strict';
import test from 'node:test';
import { filterActivities, pageNumbers, pageOf, sortActivities, toggleSort } from '../src/lib/table.js';

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

test('a page holds five rows and a missing page falls back to the last one', () => {
  const many = Array.from({ length: 6 }, (_, index) => ({ garminActivityId: String(index + 1) }));
  const first = pageOf(many, 1);
  assert.equal(first.pageCount, 2);
  assert.deepEqual(
    first.rows.map((row) => row.garminActivityId),
    ['1', '2', '3', '4', '5']
  );
  assert.equal(first.from, 1);
  assert.equal(first.to, 5);
  const last = pageOf(many, 9);
  assert.equal(last.page, 2);
  assert.deepEqual(
    last.rows.map((row) => row.garminActivityId),
    ['6']
  );
  assert.equal(last.from, 6);
  assert.equal(last.to, 6);
  assert.equal(pageOf(many.slice(0, 5), 1).pageCount, 1);
  assert.equal(pageOf([], 3).from, 0);
});

test('page numbers stay short when there are many pages', () => {
  assert.deepEqual(pageNumbers(1, 3), [1, 2, 3]);
  assert.deepEqual(pageNumbers(5, 10), [1, '…', 4, 5, 6, '…', 10]);
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
